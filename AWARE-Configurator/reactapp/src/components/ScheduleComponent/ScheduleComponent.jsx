import Grid from "@mui/material/Unstable_Grid2";
import React, { useEffect } from "react";
import { Button } from "@mui/material";
import Box from "@mui/material/Box";
import "./ScheduleComponent.css";
import DeleteIcon from "@mui/icons-material/Delete";
import { useRecoilState, useRecoilValue } from "recoil";
import Field from "../Field/Field";
import {
  studyFormQuestionsState,
  studyFormScheduleConfigurationState,
} from "../../functions/atom";
import { padding } from "../../functions/utils";
import CustomizedCheckbox from "../CustomizedCheckbox/CustomizedCheckbox";

export const SET_SCHEDULES = "interval";
// Kept for backward compatibility when loading old saved configs
export const RANDOM_TRIGGERS = "random";
export const REPEAT_INTERVALS = "repeat";

export default function ScheduleComponent(input) {
  const { scheduleIndex, onDelete } = input;
  const [schedules, setSchedules] = useRecoilState(
    studyFormScheduleConfigurationState
  );
  const questions = useRecoilValue(studyFormQuestionsState);

  const updateFormByField = (fieldName, value) => {
    const newSchedules = [...schedules].map((each, idx) => {
      if (idx === scheduleIndex) {
        return { ...each, [fieldName]: value };
      }
      return each;
    });
    setSchedules(newSchedules);
  };

  useEffect(() => {
    if (!schedules[scheduleIndex].type) {
      updateFormByField("type", SET_SCHEDULES);
    }
  }, []);

  const hours = [];
  for (let i = 0; i < 24; i += 1) {
    hours.push(
      <CustomizedCheckbox
        key={i}
        recoilState={studyFormScheduleConfigurationState}
        field={`${padding(i, 2)}:00`}
        index={scheduleIndex}
        inGroup
        groupField="hours"
        label={`${padding(i, 2)}:00`}
        className="schedule-option schedule-option--time"
      />
    );
  }

  const questionList = questions.map((question, idx) => {
    return (
      <CustomizedCheckbox
        key={idx}
        recoilState={studyFormScheduleConfigurationState}
        field={`${question.id || idx + 1}`}
        index={scheduleIndex}
        inGroup
        groupField="questions"
        label={question.esm_title}
      />
    );
  });

  return (
    <div>
      <div className="schedule_vertical_layout question_border">
        <div className="schedule_horizontal_layout">
          <p className="schedule_title">Schedule {scheduleIndex + 1}</p>
          <Button>
            <DeleteIcon
              color="error"
              sx={{ fontSize: 40 }}
              onClick={() => {
                onDelete();
              }}
            >
              REMOVE SCHEDULE
            </DeleteIcon>
          </Button>
        </div>

        <p className="schedule-description">
          If desired, create multiple schedules and assign different questions
          to each schedule.
        </p>

        <Box sx={{ width: "100%" }}>
          <Field
            fieldName="Title"
            inputLabel="The schedule title"
            index={scheduleIndex}
            recoilState={studyFormScheduleConfigurationState}
            field="title"
            required
          />
          <Grid
            container
            rowSpacing={1}
            columnSpacing={{ xs: 1, sm: 2, md: 3 }}
          >
            <Grid xs={12} md={4}>
              <p className="schedule_field_name">Carrying Questions</p>
            </Grid>
            <Grid xs={12} md={8}>
              <div className="schedule_vertical_layout">
                <CustomizedCheckbox
                  key="esm_keep"
                  recoilState={studyFormScheduleConfigurationState}
                  field="esm_keep"
                  index={scheduleIndex}
                />
                <Grid width="100%">
                  <p style={{ width: "100%" }}>
                    Carrying over any unanswered EMA questions to the next EMA
                    instance
                  </p>
                </Grid>
              </div>
            </Grid>
          </Grid>
          <Grid
            container
            rowSpacing={1}
            columnSpacing={{ xs: 1, sm: 2, md: 3 }}
          >
            <Grid xs={12} md={4}>
              <p className="schedule_field_name">Included questions *</p>
            </Grid>
            <Grid xs={12} md={8}>
              <div className="schedule-selection-card">
                <p className="schedule-selection-title">Question set</p>
                <p className="schedule-selection-copy">
                  Pick the questions that should be shown when this schedule is
                  triggered.
                </p>
                <div className="schedule-question-list">{questionList}</div>
              </div>
            </Grid>
          </Grid>
          <Grid
            container
            rowSpacing={1}
            columnSpacing={{ xs: 1, sm: 2, md: 3 }}
          >
            <Grid xs={12} md={4}>
              <p className="schedule_field_name">Hours</p>
            </Grid>
            <Grid xs={12} md={8}>
              <div className="schedule-selection-card">
                <p className="schedule-selection-title">Time slots</p>
                <p className="schedule-selection-copy">
                  Choose every hour when this schedule should trigger.
                </p>
                <div className="schedule-options-grid schedule-options-grid--hours">
                  {hours}
                </div>
              </div>
            </Grid>
          </Grid>
          <Grid
            container
            rowSpacing={1}
            columnSpacing={{ xs: 1, sm: 2, md: 3 }}
          >
            <Grid xs={12} md={4} />
            <Grid xs={12} md={8}>
              <p className="schedule-helper-copy" style={{ width: "100%" }}>
                Notification sent at the determined hours.
              </p>
            </Grid>
          </Grid>
          <Field
            fieldName="Expiration (seconds)"
            inputLabel="Time before the ESM expires after delivery"
            index={scheduleIndex}
            recoilState={studyFormScheduleConfigurationState}
            field="expiration"
            type="number"
            defaultNum={60}
          />
          <Field
            fieldName="Notification body"
            inputLabel="Message shown in the notification"
            index={scheduleIndex}
            recoilState={studyFormScheduleConfigurationState}
            field="notification_body"
          />
        </Box>
      </div>
    </div>
  );
}
