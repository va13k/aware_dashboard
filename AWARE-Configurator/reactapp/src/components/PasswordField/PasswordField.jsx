import React, { useEffect, useState } from "react";
import "./PasswordField.css";
import { TextField, IconButton, InputAdornment } from "@mui/material";
import Visibility from "@mui/icons-material/Visibility";
import VisibilityOff from "@mui/icons-material/VisibilityOff";

import { useRecoilState } from "recoil";
import Grid from "@mui/material/Unstable_Grid2";

export default function PasswordField(inputs) {
  const {
    fieldName, // mandatory feature, field's name
    recoilState, // mandatory feature, recoil state to store current field's value
    field, // mandatory feature, field's key in storage

    inputLabel, // optional feature, TextInput's inline description
    description, // optional feature
    required, // optional feature
    onReveal, // optional feature, async () => string; fills an empty field on
    // the first reveal, for values the form cannot load up front
  } = inputs;

  const [isError, setIsError] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [isRevealing, setIsRevealing] = useState(false);
  let information;
  let setInformation;
  if (recoilState === undefined) {
    [information, setInformation] = useState({});
  } else {
    [information, setInformation] = useRecoilState(recoilState);
  }

  const updateFormByField = (curFieldName, curValue) => {
    setInformation({
      ...information,
      [curFieldName]: curValue,
    });
  };

  // Reveal the stored value only when the researcher asks for it, so a page
  // visit never carries the secret into the browser on its own. Fetched once:
  // an already-filled field is the researcher's own edit and is left alone.
  const toggleVisibility = async () => {
    const revealing = !showPassword;
    setShowPassword(revealing);
    if (!revealing || !onReveal || information[field]) {
      return;
    }
    setIsRevealing(true);
    try {
      const value = await onReveal();
      if (value) {
        // Functional update: `information` is stale by the time this resolves.
        setInformation((current) => ({ ...current, [field]: value }));
      }
    } finally {
      setIsRevealing(false);
    }
  };

  // required validation logic
  useEffect(() => {
    if (required) {
      if (information[field] === "") {
        setIsError(true);
      } else {
        setIsError(false);
      }
    }
  }, [information[field]]);

  return (
    <Grid container rowSpacing={1} columnSpacing={{ xs: 1, sm: 2, md: 3 }}>
      <Grid xs={12} md={3}>
        {/* <p className="field_name">{fieldName}</p> */}
        <p className="field_name">{fieldName}</p>
      </Grid>
      <Grid xs={12} md={9}>
        <TextField
          error={isError}
          type={showPassword ? "text" : "password"}
          required={required === undefined ? false : required}
          id="outlined-basic"
          label={inputLabel}
          variant="outlined"
          style={{ width: "100%" }}
          value={information[field] || ""}
          onChange={(event) => {
            updateFormByField(field.toString(), event.target.value);
          }}
          InputProps={{
            endAdornment: (
              <InputAdornment position="end">
                <IconButton
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  onClick={toggleVisibility}
                  disabled={isRevealing}
                  edge="end"
                >
                  {showPassword ? <VisibilityOff /> : <Visibility />}
                </IconButton>
              </InputAdornment>
            ),
          }}
        />
        {description === undefined ? "" : <Grid xs={12} md={3} />}
        {description === undefined ? (
          ""
        ) : (
          <Grid xs={12} md={9}>
            <p className="description" style={{ width: "100%" }}>
              {description}
            </p>
          </Grid>
        )}
      </Grid>
    </Grid>
  );
}
