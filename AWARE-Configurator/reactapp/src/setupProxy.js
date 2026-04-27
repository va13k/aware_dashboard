const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = function (app) {
  if (!process.env.REACT_APP_BACKEND_URL) {
    throw new Error("REACT_APP_BACKEND_URL is not set in .env.development");
  }
  app.use(
    "/configurator",
    createProxyMiddleware({
      target: process.env.REACT_APP_BACKEND_URL,
      changeOrigin: true,
    }),
  );
};
