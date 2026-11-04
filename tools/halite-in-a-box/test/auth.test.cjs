const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

// Load the production module with Electron imports removed. Network and process
// configuration are isolated per test; no Electron installation is required.
const source = fs.readFileSync(path.join(__dirname, '../src/util.js'), 'utf8')
    .replace(/^import .*;\r?$/gm, '')
    .replace(/^export /gm, '');
const configuration = {
    HALITE_OAUTH_CLIENT_ID: 'test-client',
    HALITE_OAUTH_CLIENT_SECRET: 'test-secret',
    HALITE_OAUTH_REFRESH_TOKEN: 'test-refresh',
    HALITE_IAP_AUDIENCE: 'test-audience',
};

function load({ env = configuration, respond } = {}) {
    let now = 0;
    const calls = [];
    const context = {
        process: { env: { ...env } },
        Date: { now: () => now },
        window: {
            FormData,
            fetch: async (...args) => {
                calls.push(args);
                return respond ? respond(...args) : {
                    ok: true, status: 200,
                    json: async () => ({ id_token: 'test-id-token', expires_in: 3600 }),
                };
            },
        },
    };
    vm.runInNewContext(source + '\nthis.auth = { getAuthToken, download };', context);
    return { ...context.auth, calls, env: context.process.env, advance: (ms) => { now += ms; } };
}

test('missing and blank configuration reject before making a network request', async () => {
    const empty = load({ env: {} });
    const promise = empty.download('asset.zip');
    assert.equal(typeof promise.then, 'function');
    await assert.rejects(promise, (error) => {
        for (const name of Object.keys(configuration)) assert.ok(error.message.includes(name));
        return true;
    });
    assert.equal(empty.calls.length, 0);
    const partial = load({ env: { ...configuration, HALITE_OAUTH_CLIENT_SECRET: '   ' } });
    await assert.rejects(partial.getAuthToken(), /HALITE_OAUTH_CLIENT_SECRET/);
    assert.equal(partial.calls.length, 0);
});

test('runtime configuration is read when authentication is requested', async () => {
    const app = load({ env: {} });
    Object.assign(app.env, configuration);
    assert.equal(await app.getAuthToken(), 'test-id-token');
    const [url, options] = app.calls[0];
    assert.equal(url, 'https://www.googleapis.com/oauth2/v4/token');
    assert.equal(options.method, 'POST');
    assert.deepEqual(Object.fromEntries(options.body), {
        client_id: configuration.HALITE_OAUTH_CLIENT_ID,
        client_secret: configuration.HALITE_OAUTH_CLIENT_SECRET,
        refresh_token: configuration.HALITE_OAUTH_REFRESH_TOKEN,
        grant_type: 'refresh_token',
        audience: configuration.HALITE_IAP_AUDIENCE,
    });
});

test('downloads preserve URL, Bearer authorization and response identity', async () => {
    const response = { ok: true, payload: 'asset' };
    const app = load({ respond: async (url) => url.endsWith('/token')
        ? { ok: true, json: async () => ({ id_token: 'test-id-token' }) }
        : response });
    assert.equal(await app.download('assets/game.zip'), response);
    const [url, options] = app.calls[1];
    assert.equal(url, 'https://halite.io/assets/game.zip');
    assert.equal(options.headers.Authorization, 'Bearer test-id-token');
});

test('token cache expires at 45 minutes and respects shorter lifetimes', async () => {
    for (const [expires, deadline] of [[3600, 2700], [120, 60], [30, 0], [0, 0], [-10, 0]]) {
        const app = load({ respond: async () => ({ ok: true,
            json: async () => ({ id_token: 'test-id-token', expires_in: expires }) }) });
        await app.getAuthToken();
        if (deadline > 0) {
            app.advance(deadline * 1000 - 1);
            await app.getAuthToken();
            assert.equal(app.calls.length, 1);
            app.advance(1);
        }
        await app.getAuthToken();
        assert.equal(app.calls.length, 2);
    }
});

test('HTTP authentication failures omit response content and stop asset requests', async () => {
    let readBody = false;
    const app = load({ respond: async () => ({ ok: false, status: 401,
        json: async () => { readBody = true; return { error: 'private-response' }; } }) });
    await assert.rejects(app.download('asset.zip'), /^Error: Asset authentication failed \(HTTP 401\)$/);
    assert.equal(readBody, false);
    assert.equal(app.calls.length, 1);
});

test('invalid JSON errors omit the original parse error', async () => {
    const app = load({ respond: async () => ({ ok: true,
        json: async () => { throw new Error('private-response'); } }) });
    await assert.rejects(app.getAuthToken(), /^Error: Asset authentication returned invalid JSON$/);
});

test('invalid ID token responses reject and are never cached', async () => {
    for (const result of [null, {}, { id_token: '' }, { id_token: ' ' }, { id_token: 123 }]) {
        const app = load({ respond: async () => ({ ok: true, json: async () => result }) });
        await assert.rejects(app.getAuthToken(), /did not return an ID token/);
        await assert.rejects(app.getAuthToken(), /did not return an ID token/);
        assert.equal(app.calls.length, 2);
    }
});
