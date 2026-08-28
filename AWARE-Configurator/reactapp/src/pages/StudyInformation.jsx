import "./StudyInformation.css";
import React from "react";
import Grid from "@mui/material/Unstable_Grid2";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import { useRecoilState } from "recoil";
import { useNavigate } from "react-router-dom";
import { Alert, AlertTitle, Button, ThemeProvider } from "@mui/material";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";
import {
  studyFormStudyInformationState,
  databaseInformationState,
  dataflowState,
} from "../functions/atom";
import Field from "../components/Field/Field";
import customisedTheme from "../functions/theme";
import CustomizedCheckbox from "../components/CustomizedCheckbox/CustomizedCheckbox";
import PasswordField from "../components/PasswordField/PasswordField";
import Axios from "../functions/axiosSettings";

const TITLE1 = "Study Information";
const EXPLANATION1 =
  "Basic information of the study. This information will be presented to participants upon joining your study.";

const DB_HELPER_STYLE = {
  color: "#475569",
  maxWidth: "620px",
  fontSize: "0.85rem",
  margin: "0 0 12px 32px",
};

// The served study config redacts the password when it is kept out of the
// config, so the form cannot load it. This route is gated behind the researcher
// login and is only called when the researcher clicks to reveal the field.
const loadParticipantPassword = () =>
  Axios({ method: "get", url: "get_participant_password/" })
    .then((response) => response.data?.password || "")
    .catch(() => "");

// What the deployment is running, read from the study model and the environment
// rather than from this browser. Until it answers, the page describes nothing.
const loadDeploymentFacts = () =>
  Axios({ method: "get", url: "deployment_facts/" })
    .then((response) => response.data || null)
    .catch(() => null);

const DATAFLOW_LABEL = {
  direct: "Straight to the database — phones open MySQL themselves",
  webservice:
    "Through the server — phones post over HTTP/S, carrying no database credential",
};

// Describes the webservice path, where phones hold no database credential at
// all. What is worth judging there is the hop a phone actually makes and whether
// the database the server writes to is reachable beyond this host.
function describeWebserviceSecurity(facts) {
  const https = facts.protocol === "https";
  const dbPrivate = !facts.mysql_reachable_externally;

  if (https && dbPrivate) {
    return {
      severity: "success",
      title: "Recommended setup",
      body: "Phones post over HTTPS and carry no database credential, and the database is reachable only from this host. This is the strongest combination available.",
    };
  }
  if (!https && dbPrivate) {
    return {
      severity: "warning",
      title: "Phones post over plain HTTP",
      body: "The database is private and phones carry no credential for it, but the upload itself is unencrypted, so sensor data travels in plaintext between the phone and this server. Serve the deployment over HTTPS to close that.",
    };
  }
  if (https && !dbPrivate) {
    return {
      severity: "warning",
      title: "The database port is published",
      body: "Uploads are encrypted and phones hold no credential, but MySQL is still published beyond this host even though nothing outside it needs to reach the database on this path. Redeploy to narrow the published port to this machine.",
    };
  }
  return {
    severity: "error",
    title: "Weakest option",
    body: "Uploads travel in plaintext and MySQL is published beyond this host, though nothing outside it needs the database on this path. Serve the deployment over HTTPS and redeploy to narrow the published port.",
  };
}

// Describes the security of the current SSL + password-in-config combination
// and recommends the stronger option (encrypted connection, password kept out
// of the study config) without dictating what the researcher must do.
function describeDatabaseSecurity(databaseInfo) {
  // Encryption is unconditional now, so the only thing left that varies is where
  // the password lives.
  const ssl = true;
  const passwordInConfig = !databaseInfo.config_without_password;

  if (ssl && !passwordInConfig) {
    return {
      severity: "success",
      title: "Recommended setup",
      body: "The connection is encrypted and the password is never shipped in the study config — each participant enters it when joining. This is the recommended combination.",
    };
  }
  if (ssl && passwordInConfig) {
    return {
      severity: "warning",
      title: "Password is shipped in the config",
      body: "Traffic is encrypted, but the password is embedded in the study config that devices download, so it can be read from there. For stronger protection we recommend keeping the password out of the config (participants enter it) and serving the deployment over HTTPS.",
    };
  }
  if (!ssl && !passwordInConfig) {
    return {
      severity: "warning",
      title: "Connection is not encrypted",
      body: "The password is not shipped in the config, but the database connection is unencrypted, so sensor data travels in plaintext. We recommend enabling the encrypted connection.",
    };
  }
  return {
    severity: "error",
    title: "Weakest option",
    body: "The connection is unencrypted and the password is embedded in the downloaded config, so both the data and the password are exposed on the network. We recommend enabling the encrypted connection and keeping the password out of the config.",
  };
}

/**
 * What "encrypted" is worth, in the three states a study can be in.
 *
 * Kept together so the three read against each other: only one of them leaves the
 * server unverified, and it is the one a researcher can act on.
 */
function verificationText(authority) {
  if (authority === "none") {
    return (
      <>
        <b>not verified</b> — nothing here names the authority that signed its
        certificate, so devices cannot tell your database from another server
        answering in its place.
      </>
    );
  }
  if (authority === "supplied") {
    return <>verified against the certificate authority you supplied below.</>;
  }
  return (
    <>
      verified against the authority this deployment publishes for you. Nothing
      to enter.
    </>
  );
}

export default function StudyInformation() {
  const [studyInformation] = useRecoilState(studyFormStudyInformationState);
  const [databaseInfo, setDatabaseInfo] = useRecoilState(
    databaseInformationState
  );
  const [, setDataflow] = useRecoilState(dataflowState);
  const [facts, setFacts] = React.useState(null);
  const navigateTo = useNavigate();

  React.useEffect(() => {
    let cancelled = false;
    loadDeploymentFacts().then((loaded) => {
      if (cancelled || !loaded) return;
      setFacts(loaded);
      // Kept in the shared state the rest of the form reads, so the study's own
      // dataflow is what any other page sees.
      setDataflow(loaded.android_dataflow);
    });
    return () => {
      cancelled = true;
    };
  }, [setDataflow]);

  const dataflow = facts?.android_dataflow ?? null;
  const direct = dataflow === "direct";
  // A bundled database signs its own certificate and setup publishes the authority
  // it used, so nobody is asked for anything. A named one has an authority only its
  // administrator holds, and saying so is the difference between a researcher who
  // knows to go and ask for it and one who never learns the connection is unverified.
  const externalDatabase = facts?.database_placement === "external";
  const dbSecurity = direct
    ? describeDatabaseSecurity(databaseInfo)
    : describeWebserviceSecurity(facts ?? {});

  const [blankFields, setBlankFields] = React.useState([]);
  const [open, setOpen] = React.useState(false);

  const validationClose = () => {
    setOpen(false);
    setBlankFields([]);
  };

  const checkValidation = () => {
    if (
      !("study_title" in studyInformation) ||
      !("study_description" in studyInformation) ||
      !("researcher_first" in studyInformation) ||
      !("researcher_last" in studyInformation) ||
      !("researcher_contact" in studyInformation) ||
      !studyInformation.study_title ||
      !studyInformation.study_description ||
      !studyInformation.researcher_first ||
      !studyInformation.researcher_last ||
      !studyInformation.researcher_contact
    ) {
      return false;
    }
    return true;
  };

  function alertDialog() {
    return (
      <div>
        <Dialog
          open={open}
          onClose={validationClose}
          aria-labelledby="alert-dialog-title"
          aria-describedby="alert-dialog-description"
        >
          <DialogTitle id="alert-dialog-title">
            Required fields are left blank.
          </DialogTitle>
          <DialogContent>
            <DialogContentText id="alert-dialog-description">
              Fields are missing:
              {blankFields.map((item) => (
                <li key={item}>{item}</li>
              ))}
              Are you sure going to next page?
            </DialogContentText>
          </DialogContent>
          <DialogActions>
            <Button onClick={validationClose} autoFocus>
              Cancel
            </Button>
            <Button
              onClick={() => {
                validationClose();
                navigateTo("/study/questions");
              }}
            >
              Next page
            </Button>
          </DialogActions>
        </Dialog>
      </div>
    );
  }

  function isValidEmail(email) {
    return /\S+@\S+\.\S+/.test(email);
  }

  function emailNotification() {
    if (studyInformation.researcher_contact == null) {
      return <p />;
    }
    if (!isValidEmail(studyInformation.researcher_contact)) {
      return (
        <p className="validity" style={{ color: "red" }}>
          Invalid email
        </p>
      );
    }
    return (
      <p className="validity" style={{ color: "green" }}>
        Email is valid.
      </p>
    );
  }

  return (
    <ThemeProvider theme={customisedTheme}>
      <div className="main_vertical_layout">
        <div className="border">
          <p className="title">{TITLE1}</p>
          <p className="explanation">{EXPLANATION1}</p>
          <div className="field_section">
            <Field
              fieldName="Study title"
              recoilState={studyFormStudyInformationState}
              field="study_title"
              inputLabel="Study title"
              required
            />
            <Field
              fieldName="Description"
              recoilState={studyFormStudyInformationState}
              field="study_description"
              inputLabel="Description"
              required
            />
            <Field
              fieldName="Researcher's first name"
              recoilState={studyFormStudyInformationState}
              field="researcher_first"
              inputLabel="First name"
              required
            />
            <Field
              fieldName="Researcher's last name"
              recoilState={studyFormStudyInformationState}
              field="researcher_last"
              inputLabel="Last name"
              required
            />
            <Field
              fieldName="Researcher's email"
              recoilState={studyFormStudyInformationState}
              field="researcher_contact"
              inputLabel="Email"
              required
            />
          </div>

          <Grid
            container
            rowSpacing={1}
            columnSpacing={{ xs: 1, sm: 2, md: 3 }}
          >
            <Grid xs={12} md={3} />
            <Grid xs={12} md={9}>
              {emailNotification()}
            </Grid>
          </Grid>
        </div>

        <div className="border">
          <Grid width={400} ml={5} mt={3}>
            <p className="title">How data reaches the study</p>
          </Grid>
          <Box sx={{ ml: 5, mt: 1, mb: 2, maxWidth: "680px" }}>
            <p style={{ fontWeight: 600, marginBottom: "6px" }}>
              Android phones send their data
            </p>
            <p
              style={{
                background: "#f1f5f9",
                border: "1px solid #e2e8f0",
                borderRadius: "6px",
                padding: "10px 12px",
                margin: 0,
                fontSize: "0.95rem",
              }}
            >
              {dataflow ? DATAFLOW_LABEL[dataflow] : "Reading the deployment…"}
            </p>
            <p style={DB_HELPER_STYLE}>
              iPhones always go through the server: an iPhone has no
              direct-database client, so it is not a choice this study makes.
            </p>
            <Alert severity="info" sx={{ mt: 1 }}>
              <AlertTitle>Changed by redeploying, not here</AlertTitle>
              The study address a device joined with is how it identifies the
              study it belongs to, so it cannot be moved underneath enrolled
              phones — every participant joins again from a new link or QR code.
              It also decides whether the database port is published, which
              takes effect only when the deployment is brought up again. Run{" "}
              <code>./setup.sh</code> to change it.
            </Alert>
          </Box>
        </div>

        <div className="border">
          <Grid width={400} ml={5} mt={3}>
            <p className="title">Database access</p>
          </Grid>
          <p
            style={{
              color: "#475569",
              maxWidth: "680px",
              marginLeft: "40px",
            }}
          >
            {direct
              ? "Controls how participant devices reach the study database. Recommended: require an encrypted connection and keep the password out of the study config. Password and SSL changes are applied to the participant database account when you save."
              : "Controls how this server reaches the study database. Participant phones never open it on this path — they post to the server, which performs the write. Password and SSL changes are applied to the database account when you save."}
          </p>
          <Grid container direction="column" sx={{ ml: 5, mt: 1 }}>
            {/* No longer a choice. Every account is created requiring TLS, and every
                client this deployment ships already asked for it, so a switch here
                could only ever describe a connection the database would refuse. */}
            <Alert severity="info" sx={{ mb: 2 }}>
              <AlertTitle>How this deployment stands right now</AlertTitle>
              <ul style={{ margin: "6px 0 0", paddingLeft: "1.1rem" }}>
                <li>
                  Phones reach the study{" "}
                  <b>
                    {direct
                      ? "by opening the database themselves"
                      : "through this server"}
                  </b>
                  {facts?.protocol === "https"
                    ? ", over HTTPS."
                    : ", over plain HTTP — what they upload is readable on the network."}
                </li>
                <li>
                  The database runs{" "}
                  <b>
                    {externalDatabase
                      ? "on a server you named"
                      : "on this machine"}
                  </b>
                  .
                </li>
                <li>
                  The connection{" "}
                  <b>
                    {direct
                      ? "from each participant's phone to the database"
                      : "from this server to the database"}
                  </b>{" "}
                  is <b>encrypted</b>, and{" "}
                  {verificationText(facts?.database_authority)}
                </li>
              </ul>
            </Alert>
            <Alert severity="success" sx={{ mb: 1 }}>
              <AlertTitle>
                The database connection is always encrypted
              </AlertTitle>
              {direct
                ? "Participant devices open the database over TLS, so sensor data and the account password are never sent in plaintext."
                : "This server opens the database over TLS, so the study's data is never sent in plaintext."}{" "}
              The database refuses any connection that is not encrypted.
            </Alert>
            <p style={DB_HELPER_STYLE}>
              What encryption does not do on its own is prove <i>which</i>{" "}
              server answered. A database this deployment runs signs its own
              certificate, and setup publishes the authority it signed with, so
              participant devices can check it. A database you name elsewhere
              has an authority only you can supply.
            </p>
            {externalDatabase && (
              <Alert severity="info" sx={{ mt: 1 }}>
                <AlertTitle>
                  This database needs its certificate authority from you
                </AlertTitle>
                Your database presents a certificate when something connects to
                it. Devices can only check that certificate against the
                authority that signed it — and for a database you run, only you
                can supply that. Setup cannot generate it: the authority lives
                on your server, not on this one.
                <br />
                <br />
                <b>Where to find it.</b> Whoever hosts the database publishes
                it. A managed database has it in the control panel — Google
                Cloud SQL under <i>Connections → Security</i>, DigitalOcean and
                Aiven behind a <i>Download CA certificate</i> button, Amazon RDS
                and Azure as a download in their documentation. A server your
                institution runs has an administrator who can send it. A MySQL
                server that generated its own keeps it as <code>ca.pem</code> in
                the data directory. If none of those match, search your
                provider&apos;s documentation for <i>CA certificate</i>.
                <br />
                <br />
                <b>What to paste.</b> The whole file, beginning with{" "}
                <code>-----BEGIN CERTIFICATE-----</code>. Some providers give a
                bundle holding several certificates — paste all of it. Devices
                build their trust store from what the study publishes and do not
                fall back to the authorities already on the phone, so this is
                needed even when the database uses a well-known certificate.
                <br />
                <br />
                <b>If you leave it empty</b>, the connection is still encrypted,
                so nobody on the network can read the study&apos;s data. What
                stays open is impersonation: another server on that network
                could answer in place of your database, and devices would have
                no way to tell.
              </Alert>
            )}
            {externalDatabase && (
              <TextField
                multiline
                minRows={4}
                fullWidth
                sx={{ mt: 2 }}
                label="Certificate authority (optional)"
                placeholder={
                  "-----BEGIN CERTIFICATE-----\n…\n-----END CERTIFICATE-----"
                }
                value={databaseInfo.ca_certificate || ""}
                onChange={(event) =>
                  setDatabaseInfo({
                    ...databaseInfo,
                    ca_certificate: event.target.value,
                  })
                }
                helperText={
                  "Paste the whole file, including the BEGIN and END lines. " +
                  "A bundle holding several certificates can be pasted as it is. " +
                  "Leave empty to connect encrypted without verifying the server."
                }
              />
            )}
            {externalDatabase && (
              <Alert severity="warning" sx={{ mt: 1 }}>
                <AlertTitle>
                  A certificate that cannot be read stops collection
                </AlertTitle>
                Devices treat an authority they cannot parse as a database they
                cannot reach: they keep their data and stop uploading rather
                than connecting without checking. So a truncated or half-copied
                certificate halts the study until it is corrected. Saving
                refuses a certificate it cannot read for that reason — nothing
                broken reaches the phones. Leaving the field empty is a valid
                answer: the connection stays encrypted and the server is not
                verified.
              </Alert>
            )}
            {/* Only the direct path publishes a config carrying the password, so
                this is the one control that has nothing to govern otherwise. */}
            {direct ? (
              <>
                <CustomizedCheckbox
                  recoilState={databaseInformationState}
                  field="config_without_password"
                  label="Keep the password out of the study config"
                />
                <p style={DB_HELPER_STYLE}>
                  When on, the password is not written into the study config —
                  each participant enters it when joining, so it never travels
                  in the downloaded config. When off, the config includes the
                  password and joining is automatic. The database account keeps
                  its password either way.
                </p>
              </>
            ) : null}
          </Grid>
          {/* Offered on the direct path, where a participant may have to type it
              when joining. On the webservice path the account belongs to the
              micro-server and is generated with the deployment, the way the iOS
              one already is -- there is nobody to show it to. */}
          {direct ? (
            <Box sx={{ ml: 5, mt: 1, mb: 2, maxWidth: "680px" }}>
              <PasswordField
                fieldName="Participant database password"
                recoilState={databaseInformationState}
                field="database_password"
                inputLabel="Password"
                onReveal={loadParticipantPassword}
                description="The database account password. Click the eye to reveal the one in use, or type a new one. Leaving it blank keeps the current password."
              />
            </Box>
          ) : null}
          <Box sx={{ ml: 5, mb: 2, maxWidth: "680px" }}>
            <Alert severity={dbSecurity.severity}>
              <AlertTitle>{dbSecurity.title}</AlertTitle>
              {dbSecurity.body}
            </Alert>
          </Box>
        </div>

        <Box sx={{ width: "100%" }} mt={5} marginBottom={5}>
          <Grid
            container
            rowSpacing={1}
            columnSpacing={{ xs: 1, sm: 2, md: 23 }}
          >
            <Grid xs />
            <Grid xs="auto">
              <Button
                color="main"
                variant="contained"
                onClick={() => {
                  if (checkValidation()) {
                    validationClose();
                    navigateTo("/study/questions");
                    return;
                  }

                  const missingFields = [];
                  if (!studyInformation.study_title) {
                    missingFields.push("study title");
                  }
                  if (!studyInformation.study_description) {
                    missingFields.push("study description");
                  }
                  if (!studyInformation.researcher_first) {
                    missingFields.push("researcher's first name");
                  }
                  if (!studyInformation.researcher_last) {
                    missingFields.push("researcher's last name");
                  }
                  if (!studyInformation.researcher_contact) {
                    missingFields.push("researcher's contact (email)");
                  }
                  setBlankFields(missingFields);
                  setOpen(true);
                }}
              >
                NEXT STEP: QUESTIONS
              </Button>
              {alertDialog()}
            </Grid>
          </Grid>
        </Box>
      </div>
    </ThemeProvider>
  );
}
