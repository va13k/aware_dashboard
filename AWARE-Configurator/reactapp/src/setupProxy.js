const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = function (app) {
  if (!process.env.REACT_APP_BACKEND_URL) {
    throw new Error("REACT_APP_BACKEND_URL is not set in .env.development");
  }
  const proxy = createProxyMiddleware({
    target: process.env.REACT_APP_BACKEND_URL,
    changeOrigin: true,
  });
  app.use("/configurator", proxy);
  // /studies/files/* is served unprefixed by nginx in production (and by
  // Django's fallback route when running standalone) — proxy it the same
  // way so the CRA dev server (localhost:3000) doesn't try to serve it itself.
  app.use("/studies", proxy);
};
