const gplay = require('google-play-scraper').default;
const run = async () => {
    try {
        const results = await gplay.search({
            term: 'game',
            num: 20,
            sort: gplay.sort.NEWEST
        });
        console.log('Search Results (NEWEST):', results.map(r => ({ title: r.title, score: r.score, installs: r.installs, released: r.released })));
    } catch (err) {
        console.log('Error searching newest:', err.message);
    }
};
run();
