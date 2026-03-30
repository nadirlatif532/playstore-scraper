const gplay = require('google-play-scraper');
console.log('Keys:', Object.keys(gplay));
if (gplay.collection) console.log('Collection:', gplay.collection);
if (gplay.category) console.log('Category:', gplay.category);
