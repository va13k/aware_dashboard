import axios from "axios";
import config from "../settings";

axios.defaults.xsrfHeaderName = "X-CSRFTOKEN";
axios.defaults.xsrfCookieName = "csrftoken";

const baseURL =
  process.env.NODE_ENV === "development"
    ? `${config.SERVER_BASE_PATH}/`
    : `${config.SERVER_PROTOCOL}://${config.SERVER_IP}:${config.SERVER_PORT}${config.SERVER_BASE_PATH}/`;

const Axios = axios.create({ baseURL });

export default Axios;
