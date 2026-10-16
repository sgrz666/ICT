export type SetParameter = {
  op: "set_parameter";
  entity_id: string;
  parameter: string;
  value: number;
};

export type SetView = {
  op: "set_view";
  view_id: string;
  visible: boolean;
};

export type Operation = SetParameter | SetView;

export type EditProposal = {
  route: "config" | "code";
  operations: Operation[];
  code_task?: string;
};

export type LensBinding = {
  entity_id: string;
  native_type: "IdealLens";
  parameter: "focal_length_cm";
  min: number;
  max: number;
  units_per_unit: number;
};

export type RayObject = {
  type: string;
  name?: string;
  focalLength?: number;
  [key: string]: unknown;
};

export type RayScene = {
  version: number;
  objs: RayObject[];
  [key: string]: unknown;
};
