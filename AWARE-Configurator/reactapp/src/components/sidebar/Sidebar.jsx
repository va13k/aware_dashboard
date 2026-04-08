import React from "react";
import { Link, useLocation } from "react-router-dom";
import "./Sidebar.scss";

const sidebarNavItems = [
  {
    display: "Study Information",
    to: "/study/study_information",
    section: "study_information",
  },
  {
    display: "Questions",
    to: "/study/questions",
    section: "questions",
  },
  {
    display: "Schedule Configuration",
    to: "/study/schedule_configuration",
    section: "schedule_configuration",
  },
  {
    display: "Sensor Data",
    to: "/study/sensor_data",
    section: "sensor_data",
  },
  {
    display: "Overview",
    to: "/study/overview",
    section: "overview",
  },
];

function Sidebar() {
  const location = useLocation();
  const parts = location.pathname.split("/");
  let curPath = "study_information";
  if (parts.length >= 3) {
    [, , curPath] = parts;
  }

  const activeIndex = sidebarNavItems.findIndex(
    (item) => item.section === curPath,
  );

  return (
    <nav className="sidebar" aria-label="Study configuration steps">
      <div className="sidebar__menu">
        {sidebarNavItems.map((item, index) => {
          const isActive = activeIndex === index;
          const isComplete = activeIndex > index;

          return (
            <Link to={item.to} key={item.section} className="sidebar__link">
              <div
                className={`sidebar__menu__item ${
                  isActive ? "active" : ""
                } ${isComplete ? "complete" : ""}`}
              >
                <div className="sidebar__menu__item__step">{index + 1}</div>
                <div className="sidebar__menu__item__content">
                  <div className="sidebar__menu__item__text">
                    {item.display}
                  </div>
                  <div className="sidebar__menu__item__meta">
                    {isActive ? "Current" : isComplete ? "Done" : "Next"}
                  </div>
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

export default Sidebar;
