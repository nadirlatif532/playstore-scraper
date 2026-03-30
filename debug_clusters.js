const gplay = require('google-play-scraper').default;
const run = async () => {
  try {
    const clusters = await gplay.clusters();
    console.log('Clusters found:', clusters);
  } catch (err) {
    console.log('Error fetching clusters:', err.message);
  }
};
run();
