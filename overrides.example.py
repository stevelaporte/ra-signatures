# overrides.example.py
#
# Copy this file to overrides.py to enable overrides. overrides.py is
# gitignored, so your real entries stay local.
#
# Overrides replace the "currently playing" section of a user's signature
# with whatever you define, instead of pulling it from the RA API. Real
# account stats (hardcore points, softcore points, mastery count) always
# come from the live API.
#
# Keys must be lowercase usernames; lookup is case-insensitive.
#
# Fields (all optional; sensible defaults apply if omitted):
#   Title            - game title to display
#   ConsoleName      - platform text
#   ConsoleID        - RA console ID (int); enables the console icon on the
#                      Platform line. Omit for text-only.
#   ImageIcon        - game icon in the top-right corner. If omitted, uses
#                      ./overrides/<username>.png when that file exists.
#                      You can also set:
#                         "local:./overrides/somefile.png"  (a different local file)
#                         "/Images/012345.png"               (RA-hosted path)
#                         None                                (force no icon)
#   RichPresenceMsg  - the "Currently: ..." line text
#
# overrides.py is loaded once at startup. After editing it, restart the
# service, then clear that user's cache:
#   curl -X POST http://127.0.0.1:5000/invalidate/<username>

OVERRIDES = {
    "someusername": {
        "Title": "Barbie Dreamhouse Adventures",
        "ConsoleName": "PC",
        # "ConsoleID": 7,   # IDs come from API_GetConsoleIDs (e.g. 7 = NES)
        "RichPresenceMsg": "Decorating the Dreamhouse",
        # drop ./overrides/someusername.png and it's picked up automatically
    },
}
