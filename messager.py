class colors:
    DEFAULT = "\033[38;5;230m"
    WARNING = "\033[38;5;214m"
    ERR = "\033[38;5;196m"
    TEXT = "\033[38;5;45m"
    DATA1 = "\033[38;5;82m"
    DATA2 = "\033[38;5;99m"
    RESET = "\033[0m"

def warn(s, c="!!"):
    print("%s[%s] %s%s" % (colors.WARNING, c, s, colors.RESET))

def err(s, c="!!!"):
    print("%s[%s] %s%s" % (colors.ERR, c, s, colors.RESET))

def text(s, c="!"):
    print("%s[%s] %s%s%s" % (colors.DEFAULT, c, colors.TEXT, s, colors.RESET))

def parse(s, c1, c2, c3=""):
    ret = [c2]
    for i in s.split(" "):
        try:
            int(i)
            ret.append("%s%s%s" % (c3 if i == "0" and c3 else c1, i, c2))
        except:
            ret.append(i)
    return " ".join(ret)

def textHighlight(s, c="!"):
    print("%s[%s]%s%s" % (colors.DEFAULT, c, parse(s, colors.DATA1, colors.TEXT, colors.ERR), colors.RESET))

def main():
    warn("Cat!")
    text("Cat!", "*")
    text("Cat!")
    err("Cat!")
    textHighlight("13 Cats!")
    textHighlight("0 Cats :/")


if(__name__ == "__main__"):
    main()
