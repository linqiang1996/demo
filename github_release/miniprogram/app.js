let siteConfig = {};

try {
  siteConfig = require("./site.config");
} catch (error) {
  siteConfig = {};
}

App({
  globalData: {
    apiBase: siteConfig.apiBase || "http://127.0.0.1:5050",
    accessCode: siteConfig.accessCode || "",
  },
});
