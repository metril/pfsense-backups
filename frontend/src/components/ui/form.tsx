// react-hook-form adapter kit. Each Form* wraps a primitive in a
// Controller so callers can stop hand-rolling { value, onChange }
// plumbing. Field-level subscriptions: flipping one Switch re-renders
// only its Controller, not the rest of the form.
//
// Usage:
//   const { control, handleSubmit } = useForm<MyShape>({ defaultValues });
//   <FormSwitch control={control} name="enabled" label="Enabled" />

import { Controller, type Control, type FieldPath, type FieldValues } from "react-hook-form";
import { cn } from "@/lib/cn";
import { Input } from "@/components/ui/Input";
import { Switch } from "@/components/ui/Switch";
import { Checkbox } from "@/components/ui/Checkbox";
import { Select, type SelectOption } from "@/components/ui/Select";
import { CronEditor } from "@/components/cron/CronEditor";

type Base<T extends FieldValues> = {
  control: Control<T>;
  name: FieldPath<T>;
};

// -------------------- text/number/password --------------------

type FormInputProps<T extends FieldValues> = Base<T> & {
  type?: "text" | "password" | "url" | "email" | "number" | "date";
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  id?: string;
  className?: string;
  "aria-label"?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
  /** Coerce empty/NaN to a fallback when the field is numeric. */
  numericFallback?: number;
  /** Numeric fields only: empty input writes ``null`` (a deliberate
   *  "clear this override") instead of ``undefined`` ("not provided",
   *  which update endpoints treat as unchanged). */
  nullable?: boolean;
};

export function FormInput<T extends FieldValues>({
  control,
  name,
  type = "text",
  numericFallback,
  nullable = false,
  ...rest
}: FormInputProps<T>) {
  const isNumber = type === "number";
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <Input
          {...rest}
          type={type}
          // Coerce undefined/null to "" so React doesn't flip between
          // controlled and uncontrolled.
          value={field.value == null ? "" : String(field.value)}
          onChange={(e) => {
            if (isNumber) {
              const v = e.target.valueAsNumber;
              if (Number.isFinite(v)) field.onChange(v);
              else if (numericFallback !== undefined) field.onChange(numericFallback);
              else field.onChange(nullable ? null : undefined);
            } else {
              field.onChange(e.target.value);
            }
          }}
          onBlur={field.onBlur}
          ref={field.ref}
        />
      )}
    />
  );
}

// -------------------- textarea --------------------

type FormTextareaProps<T extends FieldValues> = Base<T> & {
  rows?: number;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
  className?: string;
  "aria-label"?: string;
};

export function FormTextarea<T extends FieldValues>({
  control,
  name,
  rows = 4,
  placeholder,
  disabled,
  id,
  className,
  "aria-label": ariaLabel,
}: FormTextareaProps<T>) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <textarea
          id={id}
          rows={rows}
          placeholder={placeholder}
          disabled={disabled}
          aria-label={ariaLabel}
          value={field.value == null ? "" : String(field.value)}
          onChange={(e) => field.onChange(e.target.value)}
          onBlur={field.onBlur}
          ref={field.ref}
          className={cn(
            "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm font-mono",
            "focus-visible:border-accent focus-visible:outline-none",
            "focus-visible:ring-2 focus-visible:ring-accent/60",
            "disabled:opacity-50",
            className,
          )}
        />
      )}
    />
  );
}

// -------------------- switch (button-style toggle) --------------------

type FormSwitchProps<T extends FieldValues> = Base<T> & {
  label: string;
  id?: string;
  disabled?: boolean;
};

export function FormSwitch<T extends FieldValues>({
  control,
  name,
  label,
  id,
  disabled,
}: FormSwitchProps<T>) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <Switch
          id={id}
          label={label}
          checked={Boolean(field.value)}
          onChange={field.onChange}
          disabled={disabled}
        />
      )}
    />
  );
}

// -------------------- checkbox (input-style toggle) --------------------

type FormCheckboxProps<T extends FieldValues> = Base<T> & {
  label: string;
  id?: string;
  disabled?: boolean;
  className?: string;
};

export function FormCheckbox<T extends FieldValues>({
  control,
  name,
  label,
  id,
  disabled,
  className,
}: FormCheckboxProps<T>) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <Checkbox
          id={id}
          label={label}
          checked={Boolean(field.value)}
          onChange={field.onChange}
          disabled={disabled}
          className={className}
        />
      )}
    />
  );
}

// -------------------- select (Radix dropdown) --------------------

type FormSelectProps<T extends FieldValues> = Base<T> & {
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  customOption?: { label: string } | null;
  "aria-label"?: string;
  "aria-describedby"?: string;
};

export function FormSelect<T extends FieldValues>({
  control,
  name,
  options,
  placeholder,
  disabled,
  className,
  customOption,
  "aria-label": ariaLabel,
  "aria-describedby": ariaDescribedby,
}: FormSelectProps<T>) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <Select
          value={field.value == null ? "" : String(field.value)}
          onChange={field.onChange}
          options={options}
          placeholder={placeholder}
          disabled={disabled}
          className={className}
          customOption={customOption}
          aria-label={ariaLabel}
          aria-describedby={ariaDescribedby}
        />
      )}
    />
  );
}

// -------------------- cron editor composite --------------------

type FormCronEditorProps<T extends FieldValues> = {
  control: Control<T>;
  /** Path to the cron-expression field (null or 5-field cron string). */
  valueName: FieldPath<T>;
  /** Path to the per-instance timezone override (null = inherit global). */
  timezoneName: FieldPath<T>;
  globalTimezone: string;
};

export function FormCronEditor<T extends FieldValues>({
  control,
  valueName,
  timezoneName,
  globalTimezone,
}: FormCronEditorProps<T>) {
  return (
    <Controller
      control={control}
      name={valueName}
      render={({ field: cronField }) => (
        <Controller
          control={control}
          name={timezoneName}
          render={({ field: tzField }) => (
            <CronEditor
              value={(cronField.value as string | null) ?? null}
              onChange={cronField.onChange}
              timezone={(tzField.value as string | null) ?? null}
              globalTimezone={globalTimezone}
              onTimezoneChange={tzField.onChange}
            />
          )}
        />
      )}
    />
  );
}
