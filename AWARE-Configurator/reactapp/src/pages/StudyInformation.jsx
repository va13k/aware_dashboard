import "./StudyInformation.css";
import React from "react";
import Grid from "@mui/material/Unstable_Grid2";
import Box from "@mui/material/Box";
import { useRecoilState } from "recoil";
import { useNavigate } from "react-router-dom";
import { Button, ThemeProvider } from "@mui/material";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";
import { studyFormStudyInformationState } from "../functions/atom";
import Field from "../components/Field/Field";
import customisedTheme from "../functions/theme";

const TITLE1 = "Study Information";
const EXPLANATION1 =
  "Basic information of the study. This information will be presented to participants upon joining your study.";

export default function StudyInformation() {
  const [studyInformation] = useRecoilState(studyFormStudyInformationState);
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
