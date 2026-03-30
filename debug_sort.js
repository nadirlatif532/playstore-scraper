const gplay = require('google-play-scraper').default;
console.log('Sort keys:', Object.keys(gplay.sort));
for (const key of Object.keys(gplay.sort)) {
    console.log(`${key}: ${gplay.sort[key]}`);
}
