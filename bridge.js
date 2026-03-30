const scraper = require('google-play-scraper');
const gplay = scraper.default || scraper;

const action = process.argv[2];
// Ensure we have a valid params object even if passed as empty
const params = JSON.parse(process.argv[3] || '{}');

const methods = {
    list: (p) => gplay.list(p),
    search: (p) => gplay.search(p),
    similar: (p) => gplay.similar(p),
    suggest: (p) => gplay.suggest(p),
    app: (p) => gplay.app(p)
};

/**
 * Ensures that the output is fully written and flushed to the OS 
 * before the process exits. This prevents truncation on large payloads.
 */
function sendResponse(data, exitCode = 0) {
    const payload = JSON.stringify(data) + '\n';
    const stream = exitCode === 0 ? process.stdout : process.stderr;
    
    if (!stream.write(payload)) {
        stream.once('drain', () => process.exit(exitCode));
    } else {
        // Use nextTick to ensure the write operation has finished its current cycle
        process.nextTick(() => process.exit(exitCode));
    }
}

if (methods[action]) {
    methods[action](params)
        .then(data => {
            sendResponse(data, 0);
        })
        .catch(err => {
            sendResponse({ error: err.message }, 1);
        });
} else {
    sendResponse({ error: `Action ${action} not found` }, 1);
}