import Grid from "@mui/material/Unstable_Grid2";
import React, { useEffect } from "react";
import {
  Button,
  FormControlLabel,
  MenuItem,
  Radio,
  RadioGroup,
  Select,
} from "@mui/material";
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

const DAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

// An iPhone's schedule is a list of hours and nothing else: its config carries
// `hours` and has no notion of a random draw or a repeating interval. Android's
// scheduler has all three (`TRIGGER_RANDOM`, `TRIGGER_INTERVAL`), so the two
// types below are offered and labelled for what they are rather than hidden --
// a study with Android participants is the ordinary case.
//
// What an iPhone does instead is not nothing, and saying so is the point: the
// generator turns a random window into the hours it spans, and a repeating
// interval into every hour. A researcher choosing one of these is choosing
// different behaviour per platform, and should be choosing it knowingly.
const SCHEDULE_TYPES = [
  {
    value: SET_SCHEDULES,
    label: "Set schedules",
    androidOnly: false,
  },
  {
    value: RANDOM_TRIGGERS,
    label: "Random triggers",
    androidOnly: true,
    iosNote:
      "Android draws the triggers at random inside the window. An iPhone has no random scheduler, so it is given every hour the window spans and fires on the hour.",
  },
  {
    value: REPEAT_INTERVALS,
    label: "Repeat intervals",
    androidOnly: true,
    iosNote:
      "Android repeats on the interval. An iPhone has no repeating scheduler, so it is given every hour of the day.",
  },
];

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

  const days = DAYS.map((day, idx) => (
    <CustomizedCheckbox
      key={idx}
      recoilState={studyFormScheduleConfigurationState}
      field={day}
      index={scheduleIndex}
      inGroup
      groupField="days"
      label={day}
      className="schedule-option"
    />
  ));

  // The two ends of a random window. Written back on click rather than through
  // Field, because these are the only two settings here whose value is an hour
  // chosen from a list rather than typed.
  const hourOptions = (field) =>
    Array.from({ length: 24 }, (unusedValue, i) => {
      const value = `${padding(i, 2)}:00`;
      return (
        <MenuItem
          key={i}
          value={value}
          onClick={() => updateFormByField(field, value)}
        >
          {value}
        </MenuItem>
      );
    });

  const schedule = schedules[scheduleIndex];
  const scheduleType = schedule.type || SET_SCHEDULES;
  const chosenType = SCHEDULE_TYPES.find((each) => each.value === scheduleType);

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
              <p className="schedule_field_name">Schedule type</p>
            </Grid>
            <Grid xs={12} md={8}>
              <RadioGroup value={scheduleType} name="schedule" row>
                {SCHEDULE_TYPES.map((each) => (
                  <FormControlLabel
                    key={each.value}
                    value={each.value}
                    control={
                      <Radio
                        onClick={() => updateFormByField("type", each.value)}
                      />
                    }
                    label={
                      each.androidOnly ? `${each.label} (Android)` : each.label
                    }
                  />
                ))}
              </RadioGroup>
              {chosenType?.iosNote && (
                <p className="schedule-helper-copy">{chosenType.iosNote}</p>
              )}
            </Grid>
          </Grid>

          {scheduleType === SET_SCHEDULES && (
            <>
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
              <Grid
                container
                rowSpacing={1}
                columnSpacing={{ xs: 1, sm: 2, md: 3 }}
              >
                <Grid xs={12} md={4}>
                  <p className="schedule_field_name">Days</p>
                </Grid>
                <Grid xs={12} md={8}>
                  <div className="schedule-selection-card">
                    <p className="schedule-selection-title">Days of the week</p>
                    <p className="schedule-selection-copy">
                      Leave every day unticked to trigger on all of them.
                    </p>
                    <div className="schedule-options-grid">{days}</div>
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
                    Notification sent at the determined days.
                  </p>
                </Grid>
              </Grid>
            </>
          )}

          {scheduleType === RANDOM_TRIGGERS && (
            <>
              <Grid
                container
                rowSpacing={1}
                columnSpacing={{ xs: 1, sm: 2, md: 3 }}
              >
                <Grid xs={12} md={4}>
                  <p className="schedule_field_name">Start time</p>
                </Grid>
                <Grid xs={12} md={8}>
                  <Select
                    required
                    style={{ width: "100%" }}
                    id="random-triggers-first-hour"
                    value={schedule.firsthour || "08:00"}
                  >
                    {hourOptions("firsthour")}
                  </Select>
                </Grid>
                <Grid xs={12} md={4}>
                  <p className="schedule_field_name">End time</p>
                </Grid>
                <Grid xs={12} md={8}>
                  <Select
                    required
                    style={{ width: "100%" }}
                    id="random-triggers-last-hour"
                    value={schedule.lasthour || "20:00"}
                  >
                    {hourOptions("lasthour")}
                  </Select>
                </Grid>
              </Grid>
              <Field
                fieldName="Number of triggers"
                recoilState={studyFormScheduleConfigurationState}
                index={scheduleIndex}
                field="randomCount"
                inputLabel="Number of notifications across the scheduled hour(s)."
                type="number"
              />
              <Field
                fieldName="Inter-notification time"
                recoilState={studyFormScheduleConfigurationState}
                index={scheduleIndex}
                field="randomInterval"
                inputLabel="Minimum time in-between two notifications (in minutes)."
                type="number"
              />
            </>
          )}

          {scheduleType === REPEAT_INTERVALS && (
            <Field
              fieldName="Repeat interval"
              recoilState={studyFormScheduleConfigurationState}
              index={scheduleIndex}
              field="repeatInterval"
              inputLabel="Triggered every X minutes"
              description="Schedule is triggered repeatedly in accordance with the specified interval (in minutes)."
              type="number"
            />
          )}

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
            description="iPhone only — the line under the notification's title, which is this schedule's name. It is the whole of what a participant reads before opening the questions. Android carries no such field and ignores this. Left empty, iPhones show “Tap to answer”."
          />
        </Box>
      </div>
    </div>
  );
}
