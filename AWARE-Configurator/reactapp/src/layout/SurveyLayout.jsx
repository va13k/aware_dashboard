import React from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "../components/sidebar/Sidebar";
import PageHeader from "../components/PageHeader/PageHeader";
import "./SurveyLayout.css";

function SurveyLayout() {
  return (
    <div>
      <div className="survey-layout__top">
        <PageHeader />
        <div className="survey-layout__steps">
          <Sidebar />
        </div>
      </div>
      <div className="survey-layout">
        <div className="survey-layout__content">
          <Outlet />
        </div>
      </div>
    </div>
  );
}

export default SurveyLayout;
