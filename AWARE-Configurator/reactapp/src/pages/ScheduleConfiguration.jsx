import React, { useEffect } from "react";
import { useRecoilState, useRecoilValue } from "recoil";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Unstable_Grid2";
import { Button, Link, ThemeProvider } from "@mui/material";
import { useNavigate } from "react-router-dom";
import "./ScheduleConfiguration.css";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";
import {
  studyFormQuestionsState,
  studyFormScheduleConfigurationState,
} from "../functions/atom";
import customisedTheme from "../functions/theme";
import ScheduleComponent, {
  SET_SCHEDULES,
} from "../components/ScheduleComponent/ScheduleComponent";

export default function ScheduleConfiguration() {
  const navigateTo = useNavigate();
  const [schedules, setSchedules] = useRecoilState(
    studyFormScheduleConfigurationState
  );

  const questions = useRecoilValue(studyFormQuestionsState);
  const [blankFields, setBlankFields] = React.useState([]);
  const [open, setOpen] = React.useState(false);
  const updateBlankFields = (name) => {
    setBlankFields((oldArray) => [...oldArray, name]);
  };

  const validationOn = () => {
    setOpen(true);
  };

  const validationClose = () => {
    setOpen(false);
    setBlankFields((oldArray) => []);
  };

  const [validation, setValidation] = React.useState(true);

  const validate = (value) => {
    setValidation(value);
  };

  const hasSelectedQuestions = (schedule) => {
    if (Array.isArray(schedule.questions)) {
      return schedule.questions.length > 0;
    }
    if (!schedule.questions || typeof schedule.questions !== "object") {
      return false;
    }
    return Object.values(schedule.questions).some(
      (value) => value === true || value === "true" || value === 1
    );
  };

  function alertDialog() {
    // console.log(blankFields);
    return (
      <div>
        <Dialog
          open={open}
          onClose={validationClose}
          aria-labelledby="alert-dialog-title"
          aria-describedby="alert-dialog-description"
        >
          <DialogTitle id="alert-dialog-title">
            Schedule has missing or invalid values
          </DialogTitle>
          <DialogContent>
            <DialogContentText id="alert-dialog-description">
              Please fix the following before continuing:
              {blankFields.map((item) => (
                <li key={item}>
                  {typeof item === "number"
                    ? `Schedule ${item + 1} — missing title or questions`
                    : item}
                </li>
              ))}
            </DialogContentText>
          </DialogContent>
          <DialogActions>
            <Button onClick={validationClose} autoFocus>
              OK
            </Button>
          </DialogActions>
        </Dialog>
      </div>
    );
  }

  const addSchedules = () => {
    const newQuestions = [
      ...schedules,
      {
        type: SET_SCHEDULES,
        firsthour: `08:00`,
        lasthour: `20:00`,
        randomCount: 6,
        randomInterval: 15,
      },
    ];
    setSchedules(newQuestions);
  };

  const deleteSchedules = (curQuestionIdx) => {
    // delete schedule
    const newQuestions = [...schedules];
    newQuestions.splice(curQuestionIdx, 1);
    setSchedules(newQuestions);
  };

  const checkValidation = () => {
    if (schedules.length === 0) return false;

    for (let i = 0; i < schedules.length; i += 1) {
      const each = schedules[i];
      if (!each.questions || !each.title || !("title" in each)) {
        return false;
      }

      if (!hasSelectedQuestions(each)) {
        return false;
      }
    }
    return true;
  };

  const scheduleList = [
    schedules.map((_, idx) => {
      return (
        <ScheduleComponent
          key={idx}
          scheduleIndex={idx}
          onDelete={() => {
            deleteSchedules(idx);
          }}
        />
      );
    }),
  ];

  return (
    <ThemeProvider theme={customisedTheme}>
      <div className="study_schedule_vertical_layout">
        {scheduleList}

        <Box sx={{ width: "100%" }} mt={5} marginBottom={5}>
          <Grid
            container
            rowSpacing={1}
            columnSpacing={{ xs: 1, sm: 2, md: 23 }}
          >
            <Grid xs={12}>
              <Button
                color="main"
                variant="contained"
                onClick={() => {
                  addSchedules();
                }}
              >
                ADD A NEW SCHEDULE
              </Button>
            </Grid>
            <Grid xs={2}>
              <Button
                color="main"
                variant="contained"
                onClick={() => {
                  navigateTo("/study/questions");
                }}
              >
                BACK
              </Button>
            </Grid>
            <Grid xs />
            <Grid xs="auto">
              <Button
                color="main"
                variant="contained"
                onClick={() => {
                  const valid = checkValidation();
                  validate(valid);
                  if (valid) {
                    navigateTo("/study/sensor_data");
                  } else {
                    if (schedules.length === 0) {
                      updateBlankFields(
                        "At least one schedule is required before proceeding."
                      );
                    } else {
                      for (let i = 0; i < schedules.length; i += 1) {
                        const each = schedules[i];
                        if (!each.questions || !each.title) {
                          updateBlankFields(i);
                        }
                      }
                    }
                    validationOn();
                  }
                }}
                // disabled={!checkValidation()}
              >
                NEXT STEP: SENSOR DATA
              </Button>
              {!validation ? alertDialog() : <div />}
            </Grid>
          </Grid>
        </Box>
      </div>
    </ThemeProvider>
  );
}
