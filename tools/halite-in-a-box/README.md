# Box<Halite>

This is ~~a heap allocated version of Halite~~ a standalone developer experience for Halite III, making it easy to iterate on your bots and try new strategies.

## Building

We embed Python with this application, to make the experience easier, but this makes building the application painful.

### Windows

This is a __REAL HACK__.

_Note: AppVeyor should be able to do this, once set up._

1. Install Python 3.7 on Windows.
2. `pip install zstd requests trueskill` (i.e. `hlt_client`'s dependencies).
3. Find the `site-packages` folder and zip its contents up as `deps.zip`. Put that into `./extra/`.
4. Find the `zstd.cp37....pyd` file in `site-packages` and copy that too as `./extra/zstd.pyd`.

### MacOS

_Note: Travis-CI builds this for us, thankfully._

From a Mac:

1. Make sure `virtualenv` and `python3` are available.
2. Go to `tools/halite-in-a-box/macos-portable-python`.
3. Run `build.sh`.
4. Copy `./dist/python-macos.app` to `../extra/python-macos`.

_What this does:_ uses `py2app` to build a distribution of Python with our dependencies pre-packaged.

### Linux

Have fun! (Linux has no prerequisites, since currently the application assumes all the requisite Python dependencies are available on the system.)

### The Application Itself

1. Copy `tools/hlt_client/hlt_client` to `tools/halite-in-a-box/extra/hlt_client`.
2. In `libhaliteviz` (in the repo root), run `npm install`.
3. From here, run `npm install`.
4. Run: `$(npm root)/.bin/electron-builder -m` (for Mac) or `./node_modules/.bin/electron-builder -w` (for Windows).
5. Wait a really long time.
6. Look at `./electron-dist`.

## Asset download authentication

Protected asset downloads require operator-provided OAuth credentials for the
asset service. The application reads these environment variables at runtime:

| Variable | Purpose |
| --- | --- |
| `HALITE_OAUTH_CLIENT_ID` | OAuth client used to exchange the refresh token |
| `HALITE_OAUTH_CLIENT_SECRET` | Secret for that OAuth client |
| `HALITE_OAUTH_REFRESH_TOKEN` | Refresh token authorized for the asset service |
| `HALITE_IAP_AUDIENCE` | Client ID of the IAP-protected asset service |

Inject the variables into the Electron process through your local secret manager
or protected shell session before starting the application. Use credentials that
you control and are authorized to use. This project does not load `.env` files.
Do not place values in source files, build configuration, packaged applications,
shell history, logs, issues, or pull requests. Each installation must receive its
own runtime configuration; distributing a shared OAuth secret in an Electron
bundle exposes it to anyone who obtains the bundle.

`getAuthToken()` still returns a promise for an ID token, and `download(asset)`
still returns a promise for the fetch response with Bearer authorization. Missing
configuration rejects the promise with the missing variable names before any
network request. Failed token requests and invalid token responses reject with
errors that omit the response body. Tokens are cached for at most 45 minutes and
refreshed sooner when the service reports a shorter lifetime.

Previously committed credentials must be revoked or rotated by their owner.
Removing them from source and Git history does not invalidate exposed credentials
or remove existing clones, forks, or GitHub pull request caches. Use a fresh clone
after a history rewrite to avoid pushing the old history back to the repository.

Run the authentication regression tests with Node.js 18 or later, without
installing Electron dependencies:

```sh
npm test
node --input-type=module --check < src/util.js
```
