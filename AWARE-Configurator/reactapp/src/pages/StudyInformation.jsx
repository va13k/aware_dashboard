import "./StudyInformation.css";
import React from "react";
import Grid from "@mui/material/Unstable_Grid2";
import Box from "@mui/material/Box";
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

// Describes the security of the current SSL + password-in-config combination
// and recommends the stronger option (encrypted connection, password kept out
// of the study config) without dictating what the researcher must do.
function describeDatabaseSecurity(databaseInfo) {
  const ssl = !!databaseInfo.require_ssl;
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

export default function StudyInformation() {
  const [studyInformation] = useRecoilState(studyFormStudyInformationState);
  const [databaseInfo] = useRecoilState(databaseInformationState);
  const dbSecurity = describeDatabaseSecurity(databaseInfo);
  const navigateTo = useNavigate();

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
            <p className="title">Database access</p>
          </Grid>
          <p
            style={{
              color: "#475569",
              maxWidth: "680px",
              marginLeft: "40px",
            }}
          >
            Controls how participant devices reach the study database.
            Recommended: require an encrypted connection and keep the password
            out of the study config. Password and SSL changes are applied to the
            participant database account when you save.
          </p>
          <Grid container direction="column" sx={{ ml: 5, mt: 1 }}>
            <CustomizedCheckbox
              recoilState={databaseInformationState}
              field="require_ssl"
              label="Require an encrypted (SSL/TLS) connection"
            />
            <p style={DB_HELPER_STYLE}>
              Participant devices must connect to the database over an encrypted
              (TLS) connection, so sensor data is never sent in plaintext. Only
              enable this if the devices support TLS — otherwise their uploads
              are rejected.
            </p>
            <CustomizedCheckbox
              recoilState={databaseInformationState}
              field="config_without_password"
              label="Keep the password out of the study config"
            />
            <p style={DB_HELPER_STYLE}>
              When on, the password is not written into the study config — each
              participant enters it when joining, so it never travels in the
              downloaded config. When off, the config includes the password and
              joining is automatic. The database account keeps its password
              either way.
            </p>
          </Grid>
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
