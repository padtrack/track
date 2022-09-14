## Links

---

### Why not use OAuth 2.0 (e.g. Bismarck)?

In short, because running a web server for OAuth 2.0 is overkill. In the past, this bot did use this type of authentication. Here's a list of reasons why it now uses Access Codes:

- Authenticating through OAuth2.0 exposes way more information than necessary, including your phone number (if available)! 
There's no way a Discord bot needs to know that.
- Access Codes last as long as the user wants. 
In comparison, OAuth2 tokens last up to two weeks. 
It is infeasible to ask users to authenticate this often.
- Access Codes don't require a web server/site to run, making the project significantly easier to self-host.
- Access Codes don't require an authorization URL to be sent to the user. 

Of course, Access Codes are not without downsides:

- The linking process with Access Codes is less user friendly. 
However, as previously mentioned, this process only needs to be done once in contrast to every two weeks.
- Access Codes are not a means of identity verification. 
In theory, a bandit could trick an unsuspecting user into giving them their Access Code, and link with the bot using it. 
However, the bot does not require such a level of verification, making this a non-concern.
