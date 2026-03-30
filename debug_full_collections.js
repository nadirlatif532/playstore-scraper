const gplay = require('google-play-scraper').default;
console.log('Collection keys:', Object.keys(gplay.collection));
for (const key of Object.keys(gplay.collection)) {
    console.log(`${key}: ${gplay.collection[key]}`);
}
