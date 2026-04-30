import { cx } from "../../lib/utils";

type SwitchProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
};

export function Switch({ checked, onChange, label }: SwitchProps) {
  return (
    <button className={cx("switch", checked && "switch--checked")} type="button" onClick={() => onChange(!checked)} aria-pressed={checked}>
      <span>{label}</span>
      <span className="switch__track">
        <span className="switch__thumb" />
      </span>
    </button>
  );
}
