import { faTrashAlt } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { Artcc, Position } from "@vatsim-vnas/js-libs/models/facilities";
import {
  Scenario,
  ScenarioAircraftAutoTrackConfiguration,
  ScenarioAircraftDifficulty,
  ScenarioAircraftFlightPlan,
  ScenarioAircraftFlightPlanRules,
  ScenarioAircraftStartingConditions,
  ScenarioAircraftStartingConditionsType,
  ScenarioTrigger,
  scenarioAircraftStartingConditionsTypeToString,
} from "@vatsim-vnas/js-libs/models/training";
import { TransponderMode } from "@vatsim-vnas/js-libs/models/vnas/aircraft";
import { GeoPoint } from "@vatsim-vnas/js-libs/models/vnas/common";
import { getEnumOptions } from "@vatsim-vnas/js-libs/utils";
import { FormikProps } from "formik";
import React, { useEffect, useMemo, useState } from "react";
import { ButtonGroup, Col, Form, Modal, Row } from "react-bootstrap";
import {
  AddIconButton,
  DeleteIconButton,
  Input,
  OrderButtonPair,
  SelectInput,
  Switch,
  Table,
  TableHeader,
  TableNoRows,
} from "src/components/ui";
import { deleteFromFormikArray } from "src/utils";

interface TrainingScenarioAircraftModalProps {
  show: boolean;
  index: number | undefined;
  artccs: Artcc[];
  formik: FormikProps<Scenario>;
  onClose: () => void;
}

const updateStartingConditions = (
  conditions: ScenarioAircraftStartingConditions,
  type: ScenarioAircraftStartingConditionsType | undefined = undefined,
) => {
  switch (type ?? conditions.type) {
    case ScenarioAircraftStartingConditionsType.Coordinates:
      conditions.coordinates ??= new GeoPoint();
      conditions.parking = undefined;
      conditions.fix = undefined;
      conditions.runway = undefined;
      conditions.distanceFromRunway = undefined;
      conditions.finalApproachCourseOffset = undefined;
      break;
    case ScenarioAircraftStartingConditionsType.Parking:
      conditions.coordinates = undefined;
      conditions.fix = undefined;
      conditions.runway = undefined;
      conditions.distanceFromRunway = undefined;
      conditions.altitude = undefined;
      conditions.speed = undefined;
      conditions.heading = undefined;
      conditions.navigationPath = undefined;
      conditions.mach = undefined;
      conditions.finalApproachCourseOffset = undefined;
      conditions.parking = conditions.parking ?? "";
      break;
    case ScenarioAircraftStartingConditionsType.FixOrFrd:
      conditions.coordinates = undefined;
      conditions.parking = undefined;
      conditions.runway = undefined;
      conditions.distanceFromRunway = undefined;
      conditions.finalApproachCourseOffset = undefined;
      conditions.fix = conditions.fix ?? "";
      conditions.altitude = conditions.altitude ?? 0;
      break;
    case ScenarioAircraftStartingConditionsType.OnRunway:
      conditions.coordinates = undefined;
      conditions.parking = undefined;
      conditions.fix = undefined;
      conditions.distanceFromRunway = undefined;
      conditions.altitude = undefined;
      conditions.speed = undefined;
      conditions.heading = undefined;
      conditions.navigationPath = undefined;
      conditions.mach = undefined;
      conditions.finalApproachCourseOffset = undefined;
      conditions.runway = conditions.runway ?? "";
      break;
    case ScenarioAircraftStartingConditionsType.OnFinal:
      conditions.coordinates = undefined;
      conditions.parking = undefined;
      conditions.fix = undefined;
      conditions.altitude = undefined;
      conditions.heading = undefined;
      conditions.navigationPath = undefined;
      conditions.mach = undefined;
      conditions.runway = conditions.runway ?? "";
      conditions.distanceFromRunway = conditions.distanceFromRunway ?? 0;
      break;
    default:
      break;
  }

  conditions.type = type ?? conditions.type;
  return conditions;
};

function TrainingScenarioAircraftModal({
  show,
  index,
  artccs,
  formik,
  onClose,
}: Readonly<TrainingScenarioAircraftModalProps>) {
  const [selectedStartingConditionType, setSelectedStartingConditionType] = useState(
    ScenarioAircraftStartingConditionsType.Coordinates,
  );

  useEffect(() => {
    if (index !== undefined) {
      setSelectedStartingConditionType(formik.values.aircraft[index].startingConditions.type);
    }
  }, [index, show]);

  const allPositions = useMemo(() => {
    const positions: Position[] = [];

    formik.values.atc.forEach((atc) => {
      if (atc.facilityId && atc.positionId) {
        const artcc = artccs.find((a) => a.id === atc.artccId)!;
        const facility = artcc.getFacility(atc.facilityId);
        const position = facility.positions?.find((p) => p.id === atc.positionId);
        if (position) {
          positions.push(position);
        }
      }
    });
    return positions;
  }, [formik.values.atc]);

  if (index === undefined) {
    return undefined;
  }

  const aircraft = formik.values.aircraft[index];

  if (!aircraft) {
    return undefined;
  }

  return (
    <Modal show={show} onHide={onClose} size="xl" backdrop="static">
      <Modal.Header className="dark-mode">
        <Modal.Title>Edit Aircraft</Modal.Title>
      </Modal.Header>
      <Modal.Body className="dark-mode">
        <h5>General</h5>
        <Row>
          <Col lg={3} className="mb-3">
            <Input formik={formik} name={`aircraft[${index}].aircraftId`} label="Callsign" placeholder="DAL123" />
          </Col>
          <Col lg={3} className="mb-3">
            <Input
              formik={formik}
              name={`aircraft[${index}].aircraftType`}
              label="Aircraft Type"
              placeholder="B738/L"
            />
          </Col>
          <Col lg={3} className="mb-3">
            <SelectInput
              formik={formik}
              name={`aircraft[${index}].transponderMode`}
              label="Transponder Mode"
              options={getEnumOptions(TransponderMode)}
            />
          </Col>
          <Col lg={3}>
            <Input
              number
              formik={formik}
              name={`aircraft[${index}].spawnDelay`}
              label="Spawn Delay (s)"
              placeholder="0"
              useUndefinedForEmpty
            />
          </Col>
        </Row>
        <Row className="mt-3">
          <Col lg={3} className="mb-3">
            <Input
              formik={formik}
              name={`aircraft[${index}].airportId`}
              label="Primary Airport"
              placeholder="BOS"
              useUndefinedForEmpty
            />
          </Col>
          <Col lg={3} className="mb-3">
            <Input
              formik={formik}
              name={`aircraft[${index}].expectedApproach`}
              label="Expected Approach"
              placeholder="I22L"
              useUndefinedForEmpty
            />
          </Col>
          <Col lg={3} className="mb-3">
            <SelectInput
              formik={formik}
              name={`aircraft[${index}].difficulty`}
              label="Difficulty"
              options={getEnumOptions(ScenarioAircraftDifficulty)}
            />
          </Col>
          <Col lg={3}>
            <Form.Group>
              <Form.Label>&nbsp;</Form.Label>
              <Switch label="On Altitude Profile" name={`aircraft[${index}].onAltitudeProfile`} formik={formik} />
            </Form.Group>
          </Col>
        </Row>
        <hr />
        <h5>Starting Conditions</h5>
        <Row>
          <Col className="mb-3">
            <Form.Group>
              <Form.Label>Starting Conditions Type</Form.Label>
              <Form.Control
                as="select"
                value={selectedStartingConditionType ?? "-1"}
                onChange={(e) => {
                  formik.setFieldValue(
                    `formik.values.aircraft[${index}].startingConditions`,
                    updateStartingConditions(
                      aircraft.startingConditions,
                      e.target.value as ScenarioAircraftStartingConditionsType,
                    ),
                  );
                  setSelectedStartingConditionType(e.target.value as ScenarioAircraftStartingConditionsType);
                }}
                style={!selectedStartingConditionType ? { color: "#939ba2" } : { color: "white" }}
              >
                {getEnumOptions(ScenarioAircraftStartingConditionsType, scenarioAircraftStartingConditionsTypeToString)}
              </Form.Control>
            </Form.Group>
          </Col>
        </Row>
        <Row>
          {selectedStartingConditionType === ScenarioAircraftStartingConditionsType.Coordinates && (
            <>
              <Col lg={3} className="mb-3">
                <Input
                  number
                  formik={formik}
                  name={`aircraft[${index}].startingConditions.coordinates.lat`}
                  label="Latitude"
                  placeholder="42.3656"
                  useUndefinedForEmpty
                />
              </Col>
              <Col lg={3} className="mb-3">
                <Input
                  number
                  formik={formik}
                  name={`aircraft[${index}].startingConditions.coordinates.lon`}
                  label="Longitude"
                  placeholder="-71.0096"
                  useUndefinedForEmpty
                />
              </Col>
            </>
          )}
          {selectedStartingConditionType === ScenarioAircraftStartingConditionsType.Parking && (
            <Col lg={3} className="mb-3">
              <Input
                formik={formik}
                name={`aircraft[${index}].startingConditions.parking`}
                label="Parking Spot"
                placeholder="B23"
              />
            </Col>
          )}
          {selectedStartingConditionType === ScenarioAircraftStartingConditionsType.FixOrFrd && (
            <Col lg={3} className="mb-3">
              <Input
                formik={formik}
                name={`aircraft[${index}].startingConditions.fix`}
                label="Fix or FRD"
                placeholder="BOS060010"
              />
            </Col>
          )}
          {(selectedStartingConditionType === ScenarioAircraftStartingConditionsType.OnFinal ||
            selectedStartingConditionType === ScenarioAircraftStartingConditionsType.OnRunway) && (
            <>
              <Col lg={3} className="mb-3">
                <Input
                  formik={formik}
                  name={`aircraft[${index}].startingConditions.runway`}
                  label="Runway"
                  placeholder="22L"
                />
              </Col>
              {selectedStartingConditionType === ScenarioAircraftStartingConditionsType.OnFinal && (
                <Col lg={3} className="mb-3">
                  <Input
                    number
                    formik={formik}
                    name={`aircraft[${index}].startingConditions.distanceFromRunway`}
                    label="Distance From Runway"
                    placeholder="0"
                  />
                </Col>
              )}
            </>
          )}
        </Row>
        {(selectedStartingConditionType === ScenarioAircraftStartingConditionsType.Coordinates ||
          selectedStartingConditionType === ScenarioAircraftStartingConditionsType.FixOrFrd ||
          selectedStartingConditionType === ScenarioAircraftStartingConditionsType.OnFinal) && (
          <Row>
            {selectedStartingConditionType !== ScenarioAircraftStartingConditionsType.OnFinal && (
              <Col lg={3} className="mb-3">
                <Input
                  number
                  formik={formik}
                  name={`aircraft[${index}].startingConditions.altitude`}
                  label="Altitude"
                  placeholder="11000"
                  useUndefinedForEmpty
                />
              </Col>
            )}
            <Col lg={3} className="mb-3">
              <Input
                number
                formik={formik}
                name={`aircraft[${index}].startingConditions.speed`}
                label="Speed"
                placeholder="250"
                useUndefinedForEmpty
              />
            </Col>
            {selectedStartingConditionType !== ScenarioAircraftStartingConditionsType.OnFinal && (
              <>
                <Col lg={3} className="mb-3">
                  <Input
                    number
                    formik={formik}
                    name={`aircraft[${index}].startingConditions.heading`}
                    label="Heading"
                    placeholder="090"
                    useUndefinedForEmpty
                  />
                </Col>
                <Col lg={3} className="mb-3">
                  <Input
                    number
                    formik={formik}
                    name={`aircraft[${index}].startingConditions.mach`}
                    label="Mach"
                    placeholder="0.80"
                    useUndefinedForEmpty
                  />
                </Col>
              </>
            )}
            {selectedStartingConditionType === ScenarioAircraftStartingConditionsType.OnFinal && (
              <Col lg={3} className="mb-3">
                <Input
                  number
                  formik={formik}
                  name={`aircraft[${index}].startingConditions.finalApproachCourseOffset`}
                  label="Final Approach Course Offset"
                  placeholder="15"
                  useUndefinedForEmpty
                />
              </Col>
            )}
          </Row>
        )}
        {(selectedStartingConditionType === ScenarioAircraftStartingConditionsType.Coordinates ||
          selectedStartingConditionType === ScenarioAircraftStartingConditionsType.FixOrFrd) && (
          <Row>
            <Col>
              <Input
                formik={formik}
                name={`aircraft[${index}].startingConditions.navigationPath`}
                label="Initial Path"
                placeholder="ROBUC ROBUC3.4R"
                useUndefinedForEmpty
              />
            </Col>
          </Row>
        )}
        <hr />
        <Row>
          <Col className="d-flex align-items-end">
            <h5>Flight Plan</h5>
          </Col>
          <Col>
            {!aircraft.flightplan ? (
              <div className="float-right m-2">
                <AddIconButton
                  text="Create Flight Plan"
                  onClick={() => {
                    formik.setFieldValue(`aircraft[${index}].flightplan`, new ScenarioAircraftFlightPlan());
                  }}
                />
              </div>
            ) : (
              <DeleteIconButton
                onClick={() => formik.setFieldValue(`aircraft[${index}].flightplan`, undefined)}
                className="float-right"
                text="Delete Flight Plan"
              />
            )}
          </Col>
        </Row>
        {aircraft.flightplan ? (
          <>
            <Row>
              <Col lg={3} className="mb-3">
                <SelectInput
                  formik={formik}
                  name={`aircraft[${index}].flightplan.rules`}
                  label="Flight Rules"
                  options={getEnumOptions(ScenarioAircraftFlightPlanRules)}
                />
              </Col>
              <Col lg={3} className="mb-3">
                <Input
                  formik={formik}
                  name={`aircraft[${index}].flightplan.departure`}
                  label="Departure"
                  placeholder="KBOS"
                />
              </Col>
              <Col lg={3}>
                <Input
                  formik={formik}
                  name={`aircraft[${index}].flightplan.destination`}
                  label="Destination"
                  placeholder="KJFK"
                />
              </Col>
            </Row>
            <Row>
              <Col lg={3} className="mb-3">
                <Input
                  number
                  formik={formik}
                  name={`aircraft[${index}].flightplan.cruiseAltitude`}
                  label="Cruise Altitude (MSL)"
                  placeholder="36000"
                />
              </Col>
              <Col lg={3} className="mb-3">
                <Input
                  number
                  formik={formik}
                  name={`aircraft[${index}].flightplan.cruiseSpeed`}
                  label="Cruise Speed (knots)"
                  placeholder="450"
                />
              </Col>
              <Col lg={3}>
                <Input
                  formik={formik}
                  name={`aircraft[${index}].flightplan.aircraftType`}
                  label="Filed Aircraft Type"
                  placeholder="B738/L"
                />
              </Col>
            </Row>
            <Row>
              <Col className="mb-3">
                <Input
                  formik={formik}
                  name={`aircraft[${index}].flightplan.route`}
                  label="Route"
                  placeholder="SSOXS6 SSOXS BUZRD SEY PARCH3"
                />
              </Col>
            </Row>
            <Row>
              <Col className="mb-3">
                <Input
                  formik={formik}
                  name={`aircraft[${index}].flightplan.remarks`}
                  label="Remarks"
                  placeholder="/V/ NEW PILOT FIRST FLIGHT ON VATSIM"
                />
              </Col>
            </Row>
          </>
        ) : (
          <Row>
            <Col className="mb-3">
              <i>No flight plan</i>
            </Col>
          </Row>
        )}
        <hr />
        <Row>
          <TableHeader
            onAdd={() => {
              const newTrigger = new ScenarioTrigger();
              const newTriggers = aircraft.presetCommands ?? [];
              newTriggers.push(newTrigger);
              formik.setFieldValue(`aircraft[${index}].presetCommands`, newTriggers);
            }}
            addButtonLabel="Add Command"
            headerLabel="Preset Commands"
          />
        </Row>
        <Row className="mt-2">
          <Col lg>
            <Form.Group>
              <Table>
                <thead>
                  <tr>
                    <th>Command</th>
                    <th className="w-0">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {aircraft.presetCommands.map((command, i) => (
                    <tr key={command.id}>
                      <td>
                        <Input
                          tableCell
                          formik={formik}
                          name={`aircraft[${index}].presetCommands[${i}].command`}
                          placeholder="ADD V S P -270 10 2500"
                        />
                      </td>
                      <td>
                        <ButtonGroup>
                          <OrderButtonPair formik={formik} name={`aircraft[${index}].presetCommands`} index={i} />
                          <DeleteIconButton
                            onClick={() => deleteFromFormikArray(formik, `aircraft[${index}].presetCommands`, command)}
                          />
                        </ButtonGroup>
                      </td>
                    </tr>
                  ))}
                  <TableNoRows rows={aircraft.presetCommands} text="No Preset Commands defined" />
                </tbody>
              </Table>
            </Form.Group>
          </Col>
        </Row>
        <hr />
        <Row>
          <Col>
            <h5>Auto Track Configuration</h5>
          </Col>
          <Col>
            {!aircraft.autoTrackConditions ? (
              <div className="float-right m-2">
                <AddIconButton
                  text="Create Auto Track Configuration"
                  onClick={() => {
                    formik.setFieldValue(
                      `aircraft[${index}].autoTrackConditions`,
                      new ScenarioAircraftAutoTrackConfiguration(),
                    );
                  }}
                />
              </div>
            ) : (
              <button
                type="button"
                className="btn btn-danger float-right m-2"
                onClick={() => formik.setFieldValue(`aircraft[${index}].autoTrackConditions`, undefined)}
              >
                <FontAwesomeIcon icon={faTrashAlt} className="mr-2" />
                Delete Auto Track Configuration
              </button>
            )}
          </Col>
        </Row>
        {aircraft.autoTrackConditions ? (
          <>
            <Row>
              <Col lg={4} className="mb-3">
                <SelectInput
                  formik={formik}
                  name={`aircraft[${index}].autoTrackConditions.positionId`}
                  label="Position"
                  options={allPositions.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                />
              </Col>
              <Col lg={4} className="mb-3">
                <Input
                  number
                  formik={formik}
                  name={`aircraft[${index}].autoTrackConditions.handoffDelay`}
                  label="Handoff Delay (s)"
                  placeholder="60"
                />
              </Col>
              <Col lg={4} className="mb-3">
                <Input
                  formik={formik}
                  name={`aircraft[${index}].autoTrackConditions.scratchPad`}
                  label="ScratchPad"
                  placeholder="I2L"
                />
              </Col>
            </Row>
            <Row>
              <Col lg={4} className="mb-3">
                <Input
                  formik={formik}
                  name={`aircraft[${index}].autoTrackConditions.interimAltitude`}
                  label="Temp Altitude"
                  placeholder="110"
                />
              </Col>
              <Col lg={4}>
                <Input
                  formik={formik}
                  name={`aircraft[${index}].autoTrackConditions.clearedAltitude`}
                  label="Cleared Altitude"
                  placeholder="240"
                />
              </Col>
            </Row>
          </>
        ) : (
          <Row>
            <Col>
              <i>No Auto Track Configuration</i>
            </Col>
          </Row>
        )}
        <hr />
      </Modal.Body>
      <Modal.Footer className="dark-mode">
        <button className="btn btn-primary" type="button" onClick={onClose}>
          Done
        </button>
      </Modal.Footer>
    </Modal>
  );
}

export default TrainingScenarioAircraftModal;
