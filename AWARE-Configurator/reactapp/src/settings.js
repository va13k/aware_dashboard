const config = {
  SERVER_PROTOCOL: process.env.REACT_APP_SERVER_PROTOCOL || "http",
  SERVER_IP: process.env.REACT_APP_SERVER_IP || "localhost",
  SERVER_PORT: parseInt(process.env.REACT_APP_SERVER_PORT || "80", 10),
  SERVER_BASE_PATH: process.env.REACT_APP_SERVER_BASE_PATH || "/configurator",
  BETA_MODE: false,
};

export default config;
