import re
import functools

def multi_matcher(s, *matchers):
    '''Receives matchers as parameters and applies all of them'''
    results = [m(s) for m in matchers]
    #Get the flag that indicates wether there was a match for each matcher
    has_match = [r[0] for r in results]
    #Check if there was at least one match
    at_least_one = functools.reduce(lambda x,y: x or y, has_match)
    #Get list of matches for each matcher, delete Nones
    list_of_lists = [r[1] for r in results if r[1] is not None]
    #Flatten list of matches, ignore None
    matches = [match for single_list in list_of_lists for match in single_list]
    #If the list is empty, return None
    matches = None if len(matches)==0 else matches
    return at_least_one, matches

def base64_matcher(s, remove=False):
    regex = '(?:"|\')[A-Za-z0-9\\+\\\=\\/]{50,}(?:"|\')'
    base64images = re.compile(regex).findall(s)
    has_base64 = len(base64images) > 0
    if remove:
        return has_base64, re.sub(regex, '""', s)
    else:
        return has_base64, base64images

def create_password_matcher(keywords, prs=False):
    def keyword_matcher(s):
        #Case 1: hardcoded passwords assigned to variables (python, r, etc)
        #or values (json, csv, etc)
        #match variable names such as password, PASSWORD, pwd, pass,
        #SOMETHING_PASSWORD assigned to strings (match = and <-)

        #Matches p_w_d='something' and similar
        #pwd = re.compile('(\S*\\\*(?:\'|\")*(?:p|P)\S*(?:w|W)\S*(?:d|D)\\\*(?:\'|\")*\s*(?:=|<-|:)\s*\\\*(?:\'|\").+\\\*(?:\'|\"))')

        # Escape any non-alphanumeric chars
        escape = lambda s: s if s.isalnum() or s == ";" else "\\%s" % s
        #Matches pass='something' and similar
        # Matches charsstuffKEYWORDmorecharstuff = stuff
        # Also charsstuffKEYWORDmorecharstuff =: stuff
        #      charsstuffKEYWORDmorecharstuff = "stuff"
        #      charsstuffKEYWORDmorecharstuff => stuff
        #      charsstuffKEYWORDmorecharstuff > stuff
        # And anything of the like.
        # Also matches the whole line, makes it easier to tell false-positives
        # apart, and give you more data that may be interesting.
        pass_ = re.compile(r'([^\n]*(?:%s)[\w\-]*\ *[\-=:>]+\ *(?:(?:\'[\w]+\')|(?:"[\w]+")|(?:\w+))[^\n]*)' % "|".join("".join(map(escape, keywords)).split(";")))

        #Case 2: URLS (e.g. SQLAlchemy engines)
        #http://docs.sqlalchemy.org/en/rel_1_0/core/engines.html
        # Ok, much simplified versions, I don't even know what the previous version was supposed to be doing
        # anyway, seemed broken, should work now, at least as far as I was able to test it, please adjust if you have a better idea
        # Will technicaly accept invalid domains starting with invalid chars,
        # however it is much cleaner this way, and false-positives (for this reason)
        # will be rare, and easy to notice, anyway.
        # Important detail, only matches if the url contains the protocol.
        # But, on other hand, also matches SQL stuff, what is nice.
        urls = re.compile(r'([a-zA-Z0-9-_]{3,}:\/\/(?:[^@:]+(?::[^@:]+)?@)?(?:[\w\-]\.?)+(?:\:\d+\/*)?(?:[\w\-]*[\.\/]?)*)')

        #Case 3: Passwords in bash files (bash, psql, etc) bash parameters
        # Other stuff with cli arguments also matched!
        cli_args = re.compile(r'((?:(?:\.(?:\/+[\w\.]*)+)|python|ruby|bash|zsh|ksh|perl|ssh|net user?|curl%s%s)\ (?:[\w\_\.]*\ ?)[^\n]+)' % ("|" if prs else "", "|".join("".join(map(escape, prs)).split(";")) if prs else ""))

        # Case 4: SMB share paths!
        # (Not really "password", but so aren't URLs, and definetely interesting too!)
        # Expect a bunch of false-positives here...
        # Also matches the whole line
        shares = re.compile(r'([^\n*]*\\\\[\w\- ]+\\(?:[\w.])*[^\n*]*)')

        #Case 5: Pgpass
        #http://www.postgresql.org/docs/9.3/static/libpq-pgpass.html
        # Matches till the end of the line, passwords may have spaces!
        # Quite lazy, I know, just pretend I am just trying to avoid
        # false-negatives, that's good, I guess
        pgpass = re.compile(r'([\w\.\-]+:\d+:[^\n:]+:[^\n]+)')

        # Case 6: Proxy stuff!
        # Currently, it covers Python urrlib proxies and some Perl proxies,
        # Bash and Python requests proxies usually follow the "stuff://user:pwd@addr"
        # format, so it should be matched in the case 2.
        # Also matches till the end of the line!
        proxies = re.compile(r'((?:ProxyHandler\(|add_password\(|HTTPProxyAuth|HTTP::Proxy|->credentials\((?:(?:[\"\'\w]*\,?)+)))[^\n]*')

        #what about case 1 without quotes?
        # Done!

        #passwords assigned to variables whose names are nor similar to pwd
        #but the string seems a password
        # Too risky... The current(new) implementation is already ample enough.
        regex_list = [pass_, urls, cli_args, shares, pgpass, proxies]
        matches = regex_matcher(regex_list, s)
        has_password = len(matches) > 0
        matches = None if has_password is False else matches
        return has_password, matches
    return keyword_matcher

def password_matcher(s):
    return create_password_matcher("pass|PASS|senha|SENHA|Pass|Senha")(s)

#Checks if a string has ips
#Matching IPs with regex is a thing:
#http://stackoverflow.com/questions/10086572/ip-address-validation-in-python-using-regex
def ip_matcher(s):
    ips = re.findall(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", s)
    #Remove obvious non-dangerous matches
    allowed_ips = ['127.0.0.1', '0.0.0.0']
    # Check if valid IPs(as far as it is possible to validate anyway)
    validate = lambda a: a[0] and a[1] and a[2] and a[3]
    ips = [ip for ip in ips if ip not in allowed_ips and validate(list(map(lambda s: int(s) < 256,  ip.split("."))))] # Really wanted a one liner. Failed, but, it's close, right?
    if len(ips):
        return True, ips
    else:
        return False, None

def create_domain_matcher(domain):
    '''Returns a function that serves as a matcher for a given domain'''
    def domain_matcher(s):
        escape = lambda s: s if s.isalnum() or s == ";" else "\\%s" % s
        regex = r'((?:[\w\-]+\.)+(?:%s)(?:\.[\w\-]+)*)' % "|".join("".join(map(escape, domain)).split(";"))
        matches = re.findall(regex, s)
        if len(matches):
            return True, matches
        else:
            return False, None
    return domain_matcher


def regex_matcher(regex_list, s):
    '''Get a list of regex and return all matches, removes duplicates
    in case more than onw regex matches the same pattern (pattern location
    is taken into account to determine wheter two matches are the same).'''
    #Find matchees and position for each regex
    results = [match_with_position(regex, s) for regex in regex_list]
    #Flatten list
    results = functools.reduce(lambda x,y: x+y, results)
    #Convert to set to remove duplicates
    results = set(results)
    #Extract matches only (without position)
    results = [res[1] for res in results]
    return results

def match_with_position(regex, s):
    '''Returns a list of tuples (pos, match) for each match.'''
    return [(m.start(), m.group()) for m in regex.finditer(s)]
