import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecoilRoot, useRecoilValue } from "recoil";
import ThresholdField from "./ThresholdField";
import { accelerometerState, lightState } from "../../functions/atom";

function AccelerometerThresholdReadout() {
  const { threshold } = useRecoilValue(accelerometerState);
  return <span data-testid="stored">{String(threshold)}</span>;
}

function renderAccelerometerField() {
  return render(
    <RecoilRoot>
      <ThresholdField sensor="accelerometer" studyField={0} />
      <AccelerometerThresholdReadout />
    </RecoilRoot>
  );
}

test("offers the sensor's presets with their justification", () => {
  renderAccelerometerField();

  expect(
    screen.getByText("Record every sample (no filtering)")
  ).toBeInTheDocument();
  expect(screen.getByText("Drop sensor noise only")).toBeInTheDocument();
  expect(screen.getByText(/0.05 m\/s²/)).toBeInTheDocument();
  expect(screen.getByText("Custom")).toBeInTheDocument();
});

test("names the unit rather than a bare number", () => {
  renderAccelerometerField();
  expect(screen.getByText(/at least this much, in m\/s²/)).toBeInTheDocument();
});

test("selecting a preset stores that preset's value", async () => {
  renderAccelerometerField();

  await userEvent.click(
    screen.getByRole("radio", { name: /Movement vs. stillness/ })
  );

  expect(screen.getByTestId("stored")).toHaveTextContent("0.3");
});

test("a custom value past the sensor's range is flagged", async () => {
  renderAccelerometerField();

  await userEvent.click(screen.getByRole("radio", { name: /^Custom/ }));
  const input = screen.getByLabelText("threshold in m/s²");
  await userEvent.clear(input);
  await userEvent.type(input, "120");

  expect(screen.getByText(/the sensor records nothing/)).toBeInTheDocument();
});

test("a custom value inside the sensor's range is not flagged", async () => {
  renderAccelerometerField();

  await userEvent.click(screen.getByRole("radio", { name: /^Custom/ }));
  const input = screen.getByLabelText("threshold in m/s²");
  await userEvent.clear(input);
  await userEvent.type(input, "1.5");

  expect(
    screen.queryByText(/the sensor records nothing/)
  ).not.toBeInTheDocument();
});

test("the three-axis rule is omitted for a single-value sensor", () => {
  render(
    <RecoilRoot>
      <ThresholdField sensor="light" studyField={0} />
    </RecoilRoot>
  );

  expect(screen.queryByText(/all three axes/)).not.toBeInTheDocument();
  expect(screen.getByText(/at least this much, in lux/)).toBeInTheDocument();
});

test("renders nothing for a sensor that has no threshold setting", () => {
  const { container } = render(
    <RecoilRoot>
      <ThresholdField sensor="wifi" studyField={0} />
    </RecoilRoot>
  );

  expect(container).toBeEmptyDOMElement();
});

// A study config that never set a threshold leaves the atom empty. The field
// has to read that as "record everything" rather than leaving no tier chosen.
test("a study config with no threshold set selects unfiltered collection", () => {
  function LightReadout() {
    const light = useRecoilValue(lightState);
    return <span data-testid="light">{String(light.threshold)}</span>;
  }

  render(
    <RecoilRoot>
      <ThresholdField sensor="light" studyField={undefined} />
      <LightReadout />
    </RecoilRoot>
  );

  expect(
    screen.getByRole("radio", { name: /Record every sample/ })
  ).toBeChecked();
  expect(screen.getByTestId("light")).toHaveTextContent("undefined");
});
