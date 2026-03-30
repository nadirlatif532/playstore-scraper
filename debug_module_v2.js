const gplay = require('google-play-scraper').default;
console.log('Main Keys:', Object.keys(gplay));
if (gplay.collection) console.log('Collection Keys:', Object.keys(gplay.collection));
if (gplay.category) console.log('Category Keys:', Object.keys(gplay.category));
