import weechat
import string
import feedparser

weechat.register(
        "WeeMustFeed",
        "Bit Shift <bitshift@bigmacintosh.net>",
        "0.1.1",
        "MIT",
        "RSS/Atom/RDF aggregator for weechat",
        "",
        "UTF-8"
        )


default_settings = {
        "interval": "300",
        "feeds": ""
        }

weemustfeed_buffer = None
weemustfeed_timer = None
updating = {}
partial_feeds = {}

help_message = """
a <name> <url>   Add a feed with display name of <name> and URL of <url>.
d <name>         Delete the feed with display name <name>.
u <name> <url>   Update the feed with display name <name> to use URL <url>.
l                List all feeds known to WeeMustFeed.
?                Display this help message.
""".strip()


def show_help():
    for line in help_message.split("\n"):
        weechat.prnt(weemustfeed_buffer, "\t\t" + line)


def weemustfeed_input_cb(data, buffer, input_data):
    chunks = input_data.split()

    if chunks[0] == "a":
        if len(chunks) != 3:
            weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "Wrong number of parameters. Syntax is 'a <name> <url>'.")
            return weechat.WEECHAT_RC_ERROR
        elif any([c not in (string.ascii_letters + string.digits) for c in chunks[1]]):
            weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "Only A-Z, a-z, and 0-9 permitted in names.")
            return weechat.WEECHAT_RC_ERROR
        else:
            current_feeds = weechat.config_get_plugin("feeds").strip().split(";")

            if chunks[1] in current_feeds:
                weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "A feed with that name already exists (note: feed names are case-insensitive).")
                return weechat.WEECHAT_RC_ERROR
            else:
                current_feeds.append(chunks[1])
                weechat.config_set_plugin("feed." + chunks[1].lower() + ".url", chunks[2])
                weechat.config_set_plugin("feeds", ";".join(current_feeds))
                weechat.prnt(weemustfeed_buffer, "Added '" + chunks[1] + "'.")
                weechat.hook_process(
                        "url:" + chunks[2],
                        0,
                        "weemustfeed_update_single_feed_cb", chunks[1]
                        )
    elif chunks[0] == "d":
        if len(chunks) != 2:
            weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "Wrong number of parameters. Syntax is 'd <name>'.")
            return weechat.WEECHAT_RC_ERROR
        elif any([c not in (string.ascii_letters + string.digits) for c in chunks[1]]):
            weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "Only A-Z, a-z, and 0-9 permitted in names.")
            return weechat.WEECHAT_RC_ERROR
        else:
            current_feeds = weechat.config_get_plugin("feeds").strip().split(";")
            if not chunks[1] in current_feeds:
                weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "No such feed exists.")
                return weechat.WEECHAT_RC_ERROR
            else:
                current_feeds.remove(chunks[1])
                weechat.config_set_plugin("feeds", ";".join(current_feeds))
                weechat.prnt(weemustfeed_buffer, "Deleted '" + chunks[1] + "'.")
    elif chunks[0] == "u":
        if len(chunks) != 3:
            weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "Wrong number of parameters. Syntax is 'u <name> <url>'.")
            return weechat.WEECHAT_RC_ERROR
        elif any([c not in (string.ascii_letters + string.digits) for c in chunks[1]]):
            weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "Only A-Z, a-z, and 0-9 permitted in names.")
            return weechat.WEECHAT_RC_ERROR
        else:
            current_feeds = weechat.config_get_plugin("feeds").strip().split(";")

            if not chunks[1] in current_feeds:
                weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "No feed with that name currently exists (note: feed names are case-insensitive).")
                return weechat.WEECHAT_RC_ERROR
            else:
                weechat.config_set_plugin("feed." + chunks[1].lower() + ".url", chunks[2])
                weechat.config_set_plugin("feeds", ";".join(current_feeds))
                weechat.prnt(weemustfeed_buffer, "Updated '" + chunks[1] + "'.")
    elif chunks[0] == "l":
        if len(chunks) != 1:
            weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "Wrong number of parameters. Syntax is 'l'.")
            return weechat.WEECHAT_RC_ERROR
        else:
            current_feeds = weechat.config_get_plugin("feeds").strip().split(";")
            for feed in current_feeds:
                if feed != "":
                    weechat.prnt(weemustfeed_buffer, "\t" + feed + ": " + weechat.config_get_plugin("feed." + feed.lower() + ".url"))
    elif chunks[0] == "?":
        if len(chunks) != 1:
            weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "Wrong number of parameters. Syntax is '?'.")
            return weechat.WEECHAT_RC_ERROR
        else:
            show_help()

    return weechat.WEECHAT_RC_OK


def weemustfeed_close_cb(data, buffer):
    global weemustfeed_buffer, weemustfeed_timer

    weemustfeed_buffer = None
    weechat.unhook(weemustfeed_timer)
    weemustfeed_timer = None
    return weechat.WEECHAT_RC_OK


def weemustfeed_command_cb(data, buffer, args):
    global weemustfeed_buffer

    if weemustfeed_buffer is None:
        weemustfeed_buffer = weechat.buffer_new(
                "weemustfeed",
                "weemustfeed_input_cb", "",
                "weemustfeed_close_cb", ""
                )

        weechat.buffer_set(weemustfeed_buffer, "title",
                "WeeMustFeed - a: Add feed, d: Delete feed, u: Update URL, l: List feeds, ?: Show help")

        set_timer()

    weechat.buffer_set(weemustfeed_buffer, "display", "1") # switch to it

    return weechat.WEECHAT_RC_OK


def weemustfeed_reset_timer_cb(data, option, value):
    if weemustfeed_timer is not None:
        unset_timer()
        set_timer()
    return weechat.WEECHAT_RC_OK


def weemustfeed_update_single_feed_cb(feed, command, return_code, out, err):
    global partial_feeds

    if not feed in partial_feeds:
        partial_feeds[feed] = ""

    if return_code < 0:  # feed not done yet
        partial_feeds[feed] += out
        return weechat.WEECHAT_RC_OK
    elif return_code == 1:
        weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "Invalid URL for feed '" + feed + "'.")
        return weechat.WEECHAT_RC_ERROR
    elif return_code == 2:
        weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "Transfer error while fetching feed '" + feed + "'.")
        return weechat.WEECHAT_RC_ERROR
    elif return_code == 3:
        weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "Out of memory while fetching feed '" + feed + "'.")
        return weechat.WEECHAT_RC_ERROR
    elif return_code == 4:
        weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "Error with a file while fetching feed '" + feed + "'.")
        return weechat.WEECHAT_RC_ERROR
    else:  # all good, and we have a complete feed
        if not weechat.config_is_set_plugin("feed." + feed.lower() + ".last_id"):
            weechat.config_set_plugin("feed." + feed.lower() + ".last_id", "")
            last_id = None
        else:
            last_id = weechat.config_get_plugin("feed." + feed.lower() + ".last_id")
            if last_id == "":
                last_id = None

        parsed_feed = feedparser.parse(partial_feeds[feed] + out)

        entries = list(reversed(parsed_feed.entries))

        if last_id in [entry.id for entry in entries]:
            only_new = False
        else:
            only_new = True

        for entry in entries:
            if only_new:
                weechat.prnt(weemustfeed_buffer, "{feed}\t{title} {url}".format(**{
                    "feed": feed,
                    "title": entry.title.encode("utf-8"),
                    "url": entry.link.encode("utf-8")
                    }))
                last_id = entry.id
            elif entry.id == last_id:
                only_new = True  # everything else will be newer

        if last_id is not None:
            weechat.config_set_plugin("feed." + feed.lower() + ".last_id", last_id)

    partial_feeds[feed] = ""
    return weechat.WEECHAT_RC_OK


def weemustfeed_update_feeds_cb(data, remaining_calls):
    for feed in weechat.config_get_plugin("feeds").strip().split(";"):
        if weechat.config_is_set_plugin("feed." + feed.lower() + ".url"):
            weechat.hook_process(
                    "url:" + weechat.config_get_plugin("feed." + feed.lower() + ".url"),
                    0,
                    "weemustfeed_update_single_feed_cb", feed
                    )
        elif feed != "":
            weechat.prnt(weemustfeed_buffer, weechat.prefix("error") + "Feed '" + feed + "' has no URL set.")
    return weechat.WEECHAT_RC_OK


def set_timer():
    global weemustfeed_timer

    try:
        timer_interval = int(weechat.config_get_plugin("interval"))
    except ValueError:
        timer_interval = int(default_settings["interval"])

    weemustfeed_timer = weechat.hook_timer(
            timer_interval * 1000,
            0,
            0,
            "weemustfeed_update_feeds_cb", ""
            )


def unset_timer():
    if weemustfeed_timer is not None:
        weechat.unhook(weemustfeed_timer)


def init_script():
    global default_settings

    for option, default_value in default_settings.items():
        if not weechat.config_is_set_plugin(option):
            weechat.config_set_plugin(option, default_value)

    weechat.hook_command(
        "weemustfeed",
        "open/switch to weemustfeed buffer",
        "",
        "",
        "",
        "weemustfeed_command_cb", ""
        )

    weechat.hook_config(
        "plugins.var.python.weemustfeed.interval",
        "weemustfeed_reset_timer_cb", ""
        )


init_script()
