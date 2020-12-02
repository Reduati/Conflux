#!/usr/bin/env python3
### TODO: Transform tool into package
import sys
import bs4
import requests
### TODO: Improve project structure
import matchers
import urllib3
import messager
import datetime
import hashlib
import json
import os
import optparse
import signal
import functools

# Confluences are usually local-only, so no valid certs... :/
requests.packages.urllib3.disable_warnings(category=urllib3.exceptions.InsecureRequestWarning)

### TODO: Make BASE_ADDR a CLI argument
BASE_ADDR = "https://confluence.com"
QUERY_STR = "/dosearchsite.action?queryString=${QUERY}"
NAV_STR = "&cql=siteSearch+~+\"${QUERY}\"&startIndex=${PAGE_COUNT}" # Query --> Query...; PAGE_COUNT --> 10 * Current_Result_Page

class progress():
    """Progress bar!"""
    def __init__(self, l, c=50):
        """l:int - Maximum value - A.K.A. [l]ength
           c:int - Actual bar length - Number of chars to be printed"""
        self.l = l
        self.bar_count = 50
        return
    def print(self, curr=False, msg=""):
        """Prints the progress bar
           Format: n.nn% |...| ${curr}/l - ${msg}"""
        self.curr = curr if curr else self.curr
        empty_char = u"\u25AF"
        filled_char = u"\u25AE"
        bar_count = self.bar_count
        progress = float(self.curr)/self.l * 100
        b_progress = int(round(progress/100.0 * bar_count))
        sys.stderr.write("\r%.2f%% |%s%s%s%s%s| %i/%i - %s%s" %(progress, messager.colors.DATA2 if b_progress == bar_count else "", b_progress * filled_char, messager.colors.DATA2, (bar_count-b_progress) * empty_char, messager.colors.RESET, self.curr, self.l, msg, messager.colors.RESET))

class nprogress():
    """Suppress the progress bar"""
    def print(self, curr=False, msg=""):
        return

def sigHandler(curr, sig, frame):
    r = curr[0]
    v  = curr[1]
    rf = curr[2]
    qr = curr[3]
    cf = curr[4]
    content = curr[5]
    print("\n")
    messager.warn("Extraction stopped")
    messager.text("Exporting data", "*")
    exportContent(content, "%s_%s.json" % (qr, datetime.datetime.now().strftime("%d-%m-%y")), cf)
    if(v or not rf):
        for i in r:
            print("\t- %s" % i[1].replace("\n", "\\n"))
    if(rf):
        r = exportResults(r, rf, qr)
    messager.text("Data exported")
    messager.text("Exiting")
    sys.exit(1)

def recPrint(r):
    for i in r:
        if(isinstance(i, list)):
            recPrint(i)
        elif(isinstance(i, dict)):
            for l in i:
                print("\t\t- %s: %s")
        else:
            print("\t\t- %s" % i)

def expand(r):
    """Expands the parseResults output.
       Ex: [(url, [page1,page2,page3]), (url2, [other_page1])]
           --> [(url, page1), (url, page2), (url, page3), (url2, other_page1)]"""
    return [(r[0], i) for i in r[1]]

def debugPrint(s, r, c, p=print, a=False):
    """Simple way to check if a message should be printed or not, cleaner,
       and easier to modify if necessary.
       s:String - Message to be printed
       r:int - Required count for the message to be printed
       c:int - Count
       p:function - Print function to be used
       a:list - Any extra args to be passed to the p function"""
    a = [a] if not isinstance(a, list) and a else a
    if(c >= r):
        if(a):
            p(s,*a)
        else:
            p(s)

def checkColision(s):
    """Check if file exists, if so add a number until a unique file is found.
       In case of the file having an extension the number is added before it.
       Ex: Gr8FileName --> Gr8FileName_0 --> Gr8FileName_1 --> ...
           Gr8FileName.txt --> Gr8FileName_0.txt --> Gr8FileName_1.txt --> ..."""
    ret = s
    i = 0
    increment = (lambda a,b: (".".join(a[0:-1]),b,".",a[-1])) if "." in s else (lambda a,b: (a,b,"",""))
    while(os.path.isfile(ret)):
        ret = "%s_%i%s%s" % increment(s.split("."), i)
        i += 1
    return ret

def exportPage(page, s, dir="./"):
    """Exports page for debugging.
       page:String - Page.
       s:String - Output file name
       dir:String - Output dir"""
    os.makedirs(os.path.dirname("%s%s/" % ("./" if dir[0] != "/" else "",dir)), exist_ok=True)
    s = "./%s/%s" % (dir, s)
    a = open(s, "w+")
    a.write(page)
    a.close()

def exportContent(content, s, dir):
    """Exports page content for offline manual checking.
       page:String - Page.
       s:String - Output file name
       dir:String - Output dir"""
    a = json.dumps(content)
    s = checkColision("%s/%s" % (dir, s)).split("/")[-1]
    exportPage(a, s, dir)

def exportResults(results, s, q):
    """Exports results and urls.
       The (pseudo)library may be used for easier reading.
       results:List - parseResults output
       s:String - Output file name
       q:String - Query - Just a label, really"""
    r = "\n[=] %s:\n%s" % (q, "  \n".join(["{%s}:%s" % (i[0], i[1].replace("\n", "\\n")) for i in results]))
    a = open(s, "a+")
    a.write(r)
    a.close()
    return r

def getPage(query, pg=0, returnSoup=False):
    """Fetches the results page for a query.
       Also parses the number of result pages.
       query:String - Query.
       pg:int - Result page to be checked
       returnSoup:bool - If true, will return the BeautifulSoup object, thus returning
                         a three item tuple instead of two

        Return: {tuple}({String}resultsPage, {int}pageCount[, {BeautifulSoup object}soup if returnSoup else {Just nothing}])"""
    global BASE_ADDR
    global QUERY_STR
    global NAV_STR

    page = requests.get("%s%s%s" % (BASE_ADDR, QUERY_STR.replace("${QUERY}", query), NAV_STR.replace("${PAGE_COUNT}", str(10 * pg)).replace("${QUERY}", query) if pg else ""), verify=False).text
    sp = bs4.BeautifulSoup(page, features="lxml")
    pageCount = 0
    try:
        pageCount = 0 if "No results found for " in sp.find("div", {"class": "search-results-container"}).get_text() else int(sp.find("p", {"class": "search-results-count"}).get_text().split(".")[0].split(" ")[-1])
    except:
        if(query not in sp.find("div", {"class": "search-results-container"}).get_text()):
            messager.err("Failed to extract page count")
            print(sp.find("div", {"class": "search-results-container"}).get_text())
            n = "%s%s_%s_%s.html" % (QUERY_STR.replace("${QUERY}", query).replace("/","_"), NAV_STR.replace("${PAGE_COUNT}", str(10 * pg)).replace("${QUERY}", query) if pg else "", hashlib.md5(page.encode()).hexdigest(), datetime.datetime.now().strftime("%I-%M-%S"))
            messager.err("Exporting to file: %s" % n)
            exportPage(page, n)
        pagecount = 0
    return (page, pageCount) if not returnSoup else (page, pageCount, sp)

def parseSoup(sp):
    """Gets all links contained by the results page."""
    return [i["href"] for i in sp.find_all("a", {"class": "search-result-link visitable"})]

def parsePage(page):
    """Create a BeautifulSoup object, and return all links contained by the
       results page."""
    sp = bs4.BeautifulSoup(page, features="lxml")
    return parseSoup(sp)

def navigateResults(results):
    """Navigate all links, returning a list contaning the ulrs and corresponding pages.
       results:[String] - List with links to be visited

       Return: {list}[{tuple}({String}url, {String}content)]"""
    global BASE_ADDR

    ret = []
    for i in results:
        page = requests.get("%s%s" % (BASE_ADDR, i), verify=False)
        ret.append(["%s%s" % (BASE_ADDR, i), page.text])
    return ret

def parseResults(r, m):
    """Extracts the content from the supplied pages and matches using the
       passed matchers.
       r:[String] - Pages to be parsed
       m:[matchers objects(functions)] - parseMatchers() output

       Return: {tuple}({list}[(url, match), (url2, match2), ...], {list}[Extracted contents])"""
    ret = []
    results = []
    for i in r:
        sp = bs4.BeautifulSoup(i[1], features="lxml")
        for l in sp.find_all("br"):
            l.replace_with("\n")
        div = sp.find("div", {"id": "main-content"})
        try:
            results.append((i[0], "\n".join([l.get_text() for l in div.find_all("p")])))
        except:
            a = "b" # Do nothing
    for i in results:
        match, matches = matchers.multi_matcher(i[1], *m)
        if(match):
            ret += list(set(expand((i[0], matches))))
    return (ret, results)

def harvest(query, m, currPage=0):
    """Get and parse results.
       query:String - Keyword to search for
       m:[matchers objects(functions)] - parseMatchers() output
       currPage:int - Result page number to parse

       Return: {tuple}({int}TotalResultPageCount, {tuple}({list}[(url, match), (url2, match2), ...], {list}[Extracted contents]))"""
    ret = []
    page, pageCount, sp = getPage(query, currPage, returnSoup=True)
    results = parseSoup(sp)
    pages = navigateResults(results)
    return (pageCount, parseResults(pages, m))

def parseArgs():
    """Parses cli arguments, nothing special."""
    global BASE_ADDR

    ### TODO: Add option for inputting file containing patterns/configs(JSON?)
    parser = optparse.OptionParser(add_help_option=False)
    parser.add_option("-v", "--verbose", action="count", dest="VERBOSE", default=0)
    parser.add_option("-q", "--query", dest="QUERY", default="password;pwd;api-key;api")
    parser.add_option("-k", "--keywords", dest="KEYWORDS", default="password;pass;pwd;api-key;client-secret;client-id")
    parser.add_option("-l", "--limit", dest="LIMIT", default=False)
    parser.add_option("-o", "--out", dest="OUT", default="./out/")
    parser.add_option("-O", "--outresult", dest="OUTRESULT", default=False)
    parser.add_option("-d", "--domains", dest="DOMAINS", default="amazonaws.com")
    parser.add_option("-p", "--programs", dest="PROGRAMS", default=False)
    parser.add_option("-s", "--suppressbar", action="store_true", dest="SUPPRESSBAR")
    parser.add_option("-n", "--notstupid", action="store_true", dest="NOTSTUPID")
    parser.add_option("-h", "--help", action="store_true", dest="HELP")
    (args, p) = parser.parse_args()
    BASE_ADDR = p if p else BASE_ADDR

    if(args.HELP):
        print("Conflux is a Confluence stuff scraper!")
        print("It works by searching for each query supplied and scraping all the returned links.\n")
        print(("{3}usage: {1}./{2}%s{1} {1}{{-{0}q{1} {3}query{1}}} {{-{0}k{1} {3}keywords{1}}} {{-{0}l{1} {3}limit{1}}} {{-{0}o{1} {3}output_folder{1}}} {{-{0}O{1} {3}output_file{1}}} {{-{0}d{1} {3}domains{1}}} {{-{0}p{1} {3}programs{1}}} {{-{0}snh{1}}} {{-{0}v{1}[{0}vvv{1}]}} [{2}Confluence_URL{1}]" % sys.argv[0]).format(messager.colors.DATA1, messager.colors.TEXT, messager.colors.WARNING, messager.colors.RESET))
        print("       -%sq%s, --%squery%s: Keywords to be searched." % (messager.colors.DATA1, messager.colors.RESET, messager.colors.WARNING, messager.colors.RESET))
        print("                    \";\" separated.")
        print("       -%sk%s, --%skeywords%s: Keywords to be matched during scraping." % (messager.colors.DATA1, messager.colors.RESET, messager.colors.WARNING, messager.colors.RESET))
        print("                       Matching occurs when an assignment-like statement contaning the keyword")
        print("                       is found. Ex: stuff{Keywrd}stuff = \"Gr8Password!\"")
        print("                       \";\" separated.")
        print("       -%sl%s, --%slimit%s: Limit of search pages to be scraped per query word." % (messager.colors.DATA1, messager.colors.RESET, messager.colors.WARNING, messager.colors.RESET))
        print("       -%so%s, --%sout%s: Output folder. The parsed content is exported to a json file for each query." % (messager.colors.DATA1, messager.colors.RESET, messager.colors.WARNING, messager.colors.RESET))
        print("       -%sO%s, --%soutresult%s: Output file. The results are appended to the supplied file." % (messager.colors.DATA1, messager.colors.RESET, messager.colors.WARNING, messager.colors.RESET))
        print("                        Format: [=] QUERY\\n{url}:RESULT")
        print("       -%sd%s, --%sdomains%s: Domains to be matched. Matches subdomains for each supplied domain" % (messager.colors.DATA1, messager.colors.RESET, messager.colors.WARNING, messager.colors.RESET))
        print("                      \";\" separated.")
        print("       -%sp%s, --%sprograms%s: Programs to match when a command-line-like statement contaning" % (messager.colors.DATA1, messager.colors.RESET, messager.colors.WARNING, messager.colors.RESET))
        print("                       arguments is found. The match is fairly open, and prone to false")
        print("                       negatives, lots of them, be careful not to put something too generic here.")
        print("       -%ss%s, --%ssuppressbar%s: Suppress the progress bar." % (messager.colors.DATA1, messager.colors.RESET, messager.colors.WARNING, messager.colors.RESET))
        print("       -%sn%s, --%snotstupid%s: Drop the matches containing \\n." % (messager.colors.DATA1, messager.colors.RESET, messager.colors.WARNING, messager.colors.RESET))
        print("                        Exponentially reduces false positives.")
        print("       -%sv%s, --%sverbose%s: Verbose out. More v's may be added to increase verbosity." % (messager.colors.DATA1, messager.colors.RESET, messager.colors.WARNING, messager.colors.RESET))
        print("                      Verbose output can be identified by \"[%/.../%%%%] ...\"")
        print("       -%sh%s, --%shelp%s: Hi!" % (messager.colors.DATA1, messager.colors.RESET, messager.colors.WARNING, messager.colors.RESET))
        print("\n")
        sys.exit(0) # Don't use this in a script, really, I mean you probably won't pass arguments in a script, so
                    # it should be fine. Probably...

    return (args.QUERY, args.KEYWORDS, args.LIMIT, args.OUT, args.OUTRESULT, args.VERBOSE, args.DOMAINS, args.PROGRAMS, args.SUPPRESSBAR, args.NOTSTUPID)

def parseMatchers(kwrd, dms, prs):
    """Create matcher functions based of keywords and domains(fancy keywords...).
       The output should be used with matchers.multi_matcher, or, more appropriately,
       passed to harvest().
       kwrd:String - Keywords to match, creates a password matcher, which matches
                       variable assignments and similar looking stuff
       dms:String - Domains to be matched, locates subdomains, and should locate paths,
                      however requires some modification.

       Return: {list}[{function}matcher]"""
    ret = []
    ret.append(matchers.create_password_matcher(kwrd, prs))
    ret.append(matchers.ip_matcher)
    ret.append(matchers.create_domain_matcher(dms))
    return ret


def main():
    #print(" Conflux \n")
    print("%s\t      ::::::::   ::::::::  ::::    ::: :::::::::: :::       :::    ::: :::    ::: %s" % (messager.colors.TEXT, messager.colors.RESET))
    print("%s\t    :+:    :+: :+:    :+: :+:+:   :+: :+:        :+:       :+:    :+: :+:    :+:  %s" % (messager.colors.TEXT, messager.colors.RESET))
    print("%s\t   +:+        +:+    +:+ :+:+:+  +:+ +:+        +:+       +:+    +:+  +:+  +:+    %s" % (messager.colors.TEXT, messager.colors.RESET))
    print("%s\t  +#+        +#+    +:+ +#+ +:+ +#+ :#::+::#   +#+       +#+    +:+   +#++:+      %s" % (messager.colors.TEXT, messager.colors.RESET))
    print("%s\t +#+        +#+    +#+ +#+  +#+#+# +#+        +#+       +#+    +#+  +#+  +#+      %s" % (messager.colors.TEXT, messager.colors.RESET))
    print("%s\t#+#    #+# #+#    #+# #+#   #+#+# #+#        #+#       #+#    #+# #+#    #+#      %s" % (messager.colors.TEXT, messager.colors.RESET))
    print("%s\t########   ########  ###    #### ###        ########## ########  ###    ###       %s" % (messager.colors.TEXT, messager.colors.RESET))
    print("")
    qrs, kwrd, l, cf, rf, v, dms, prs, q, ns = parseArgs()
    m = parseMatchers(kwrd, dms, prs)

    messager.text("Query words: %s%s" % (messager.colors.RESET, qrs.split(";")[0]))
    print("\n".join(["               %s-%s %s" % (messager.colors.TEXT, messager.colors.RESET, i) for i in qrs.split(";")[1:]]))
    print("")
    #messager.text("Keywords: %s%s" % (messager.colors.RESET, qrs.split(";")[0]))
    #print("\n".join(["            %s-%s %s" % (messager.colors.TEXT, messager.colors.RESET, i) for i in kwrd.split(";")[1:]]))
    for qr in qrs.split(";"):
        r = []
        content = []
        messager.text("Retrieving pages for query: \"%s\"" % qr)
        pageCount, pages = harvest(qr, m)

        for i in pages:
            r += i
        messager.textHighlight("%i pages found!" % pageCount)
        messager.text("Navigating results and extracting (hopefully) interesting data!", "*")

        if(l and pageCount > int(l)):
            pageCount = int(l)
            messager.textHighlight("Query limited to %i result pages" % pageCount)

        prog = progress(pageCount) if not q else nprogress() # Avoids making a comparison every iteration, quite pointless, really
        print("\n")
        for i in range(1, pageCount):
            _, pages = harvest(qr, m, i)
            prog.print(i+1, messager.parse("%i results found!    \b\b\b\b" % len(pages[0]), messager.colors.DATA1, messager.colors.TEXT, messager.colors.ERR))
            debugPrint("",2,v)
            debugPrint("Result count: %i" % len(r),2,v,messager.text, "%%")
            debugPrint(pages[0],3,v,messager.text, "%%%")
            r += pages[0]
            content.append(pages[1])
            debugPrint(pages[1],4,v,messager.text, "%%%%")
            signal.signal(signal.SIGINT, functools.partial(sigHandler, [r,v,rf,qr,cf,content]))

        print("\n")
        if(ns):
            r = [(i[0], i[1]) for i in r if "\n" not in i[1]]
        if(v or not rf):
            for i in r:
                print("\t- %s" % i[1].replace("\n", "\\n"))

        exportContent(content, "%s_%s.json" % (qr, datetime.datetime.now().strftime("%d-%m-%y")), cf)
        if(rf):
            r = exportResults(r, rf, qr)
    return r

if(__name__ == "__main__"):
    main()








































#if("No results found for " in soup.find("div", {"class": "search-results-container"}).get_text()):
#    break;
