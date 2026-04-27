import "./Main.css";
import { Button, Divider, ThemeProvider, Chip } from "@mui/material";
import { useNavigate } from "react-router-dom";
import EditIcon from "@mui/icons-material/Edit";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import PhoneIphoneIcon from "@mui/icons-material/PhoneIphone";
import LockIcon from "@mui/icons-material/Lock";
import AccessTimeIcon from "@mui/icons-material/AccessTime";
import GitHubIcon from "@mui/icons-material/GitHub";
import AttachMoneyIcon from "@mui/icons-material/AttachMoney";
import Grid from "@mui/material/Unstable_Grid2";
import React from "react";
import PageHeader from "../components/PageHeader/PageHeader";
import customisedTheme from "../functions/theme";
import Axios from "../functions/axiosSettings";
import config from "../settings";

export default function Main() {
  Axios({
    method: "get",
    url: "get_token/",
  });

  const navigateTo = useNavigate();

  return (
    <div>
      <div className="main_vertical_layout">
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <p className="main_title">AWARE Configuration Page</p>
          {config.BETA_MODE && (
            <Chip
              label="BETA"
              color="warning"
              size="small"
              sx={{
                height: "20px",
                "& .MuiChip-label": {
                  px: 1,
                  fontSize: "0.75rem",
                  fontWeight: "bold",
                },
              }}
            />
          )}
        </div>
        <p className="main_description">
          Use this page to update the study configuration that is shared across
          Android and iOS deployments.
        </p>

        <ThemeProvider theme={customisedTheme}>
          <div className="main_horizontal_layout">
            <Button
              variant="contained"
              color="main"
              size="large"
              onClick={() => {
                navigateTo("/upload");
              }}
              sx={{ fontSize: "1.1rem", px: 4, py: 1.5 }}
            >
              <EditIcon sx={{ mr: 1 }} />
              Change study configuration
            </Button>
          </div>

          <Grid container spacing={2} className="main_grid">
            <Grid xs={4}>
              <AutoFixHighIcon color="main" sx={{ fontSize: 70 }} />
              <p>One editor updates the shared study source file.</p>
            </Grid>
            <Grid xs={4}>
              <PhoneIphoneIcon color="main" sx={{ fontSize: 70 }} />
              <p>Android and iOS configs are regenerated from the same data.</p>
            </Grid>
            <Grid xs={4}>
              <LockIcon color="main" sx={{ fontSize: 70 }} />
              <p>
                Deployment-level server and database settings stay managed
                outside the form.
              </p>
            </Grid>
          </Grid>
          <Grid container spacing={2} className="main_grid">
            <Grid xs={4}>
              <AccessTimeIcon color="main" sx={{ fontSize: 70 }} />
              <p>
                Researchers only update the study content they actually need.
              </p>
            </Grid>
            <Grid xs={4}>
              <GitHubIcon color="main" sx={{ fontSize: 70 }} />
              <p>
                Source code is{" "}
                <a href="https://github.com/awareframework/AWARE-Configurator">
                  publicly available
                </a>
                , and we welcome your ideas and contributions.
              </p>
            </Grid>
            <Grid xs={4}>
              <AttachMoneyIcon color="main" sx={{ fontSize: 70 }} />
              <p>AWARE is completely free to use.</p>
            </Grid>
          </Grid>
        </ThemeProvider>

        <Divider light sx={{ my: 5 }} />

        <Grid container spacing={2}>
          <Grid xs={6}>
            <p style={{ fontSize: "1.5rem", color: "black" }}>
              Experience Sampling
            </p>
            <p>
              Experience Sampling is a widely applied method to measure
              behaviour, thoughts, and feelings of study participants throughout
              their daily lives. Data is collected through self-reports
              filled-out by the study participants.
            </p>
          </Grid>
          <Grid xs={6}>
            <p style={{ fontSize: "1.5rem", color: "black" }}>About</p>
            <p>
              AWARE is a version of the AWARE Android framework dedicated to
              instrument, infer, log, and share mobile context information. It
              allows for the collection of over 25 different sensors.
            </p>
          </Grid>
        </Grid>
      </div>
    </div>
  );
}
