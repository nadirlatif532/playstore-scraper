const scraper = require('google-play-scraper');
const gplay = scraper.default || scraper;

const action = process.argv[2];
// Ensure we have a valid params object even if passed as empty
const params = JSON.parse(process.argv[3] || '{}');

const methods = {
    list: (p) => gplay.list(p),
    similar: (p) => gplay.similar(p),
    suggest: (p) => gplay.suggest(p),
    app: (p) => gplay.app(p)
};

if (methods[action]) {
    methods[action](params)
        .then(data => {
            // Log ONLY the stringified data to stdout for Python to read
            process.stdout.write(JSON.stringify(data));
            process.exit(0);
        })
        .catch(err => {
            process.stderr.write(JSON.stringify({ error: err.message }));
            process.exit(1);
        });
} else {
    process.stderr.write(JSON.stringify({ error: `Action ${action} not found` }));
    process.exit(1);
}