"use client";

import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { Form, Formik, useField, type FormikConfig, type FormikHelpers, type FormikProps } from "formik";
import type { AnyObjectSchema } from "yup";

type FormValues = Record<string, unknown>;

type BaseFormProps<Values extends FormValues> = {
  initialValues: Values;
  validationSchema?: AnyObjectSchema;
  onSubmit: (values: Values, helpers: FormikHelpers<Values>) => void | Promise<void>;
  className?: string;
  enableReinitialize?: boolean;
  children: (form: FormikProps<Values>) => ReactNode;
};

type FieldBaseProps = {
  label?: string;
  name: string;
  helperText?: string;
  className?: string;
  inputClassName?: string;
};

type BaseInputProps = FieldBaseProps & InputHTMLAttributes<HTMLInputElement>;
type BaseSelectProps = FieldBaseProps & SelectHTMLAttributes<HTMLSelectElement>;
type BaseTextareaProps = FieldBaseProps & TextareaHTMLAttributes<HTMLTextAreaElement>;

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

const fieldClassName =
  "w-full rounded border border-zinc-300 bg-white px-2 py-1 text-sm text-zinc-900 outline-none transition-colors focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

function FieldMessage({ error, helperText }: { error?: string; helperText?: string }) {
  if (error) {
    return <div className="mt-1 text-[11px] text-red-600">{error}</div>;
  }
  if (helperText) {
    return <div className="mt-1 text-[11px] text-zinc-500">{helperText}</div>;
  }
  return null;
}

export function BaseField({ label, helperText, className, inputClassName, ...props }: BaseInputProps) {
  const [field, meta] = useField(props.name);
  const error = meta.touched ? meta.error : undefined;

  return (
    <label className={cx("block", className)}>
      {label ? <div className="mb-1 text-xs font-medium text-zinc-700 dark:text-zinc-300">{label}</div> : null}
      <input {...field} {...props} className={cx(fieldClassName, inputClassName)} />
      <FieldMessage error={error} helperText={helperText} />
    </label>
  );
}

export function BaseTextarea({ label, helperText, className, inputClassName, ...props }: BaseTextareaProps) {
  const [field, meta] = useField(props.name);
  const error = meta.touched ? meta.error : undefined;

  return (
    <label className={cx("block", className)}>
      {label ? <div className="mb-1 text-xs font-medium text-zinc-700 dark:text-zinc-300">{label}</div> : null}
      <textarea {...field} {...props} className={cx(fieldClassName, inputClassName)} />
      <FieldMessage error={error} helperText={helperText} />
    </label>
  );
}

export function BaseSelect({ label, helperText, className, inputClassName, children, ...props }: BaseSelectProps) {
  const [field, meta] = useField(props.name);
  const error = meta.touched ? meta.error : undefined;

  return (
    <label className={cx("block", className)}>
      {label ? <div className="mb-1 text-xs font-medium text-zinc-700 dark:text-zinc-300">{label}</div> : null}
      <select {...field} {...props} className={cx(fieldClassName, inputClassName)}>
        {children}
      </select>
      <FieldMessage error={error} helperText={helperText} />
    </label>
  );
}

export default function BaseForm<Values extends FormValues>({
  initialValues,
  validationSchema,
  onSubmit,
  className,
  enableReinitialize = false,
  children,
}: BaseFormProps<Values>) {
  const config: FormikConfig<Values> = {
    initialValues,
    validationSchema,
    onSubmit,
    enableReinitialize,
  };

  return (
    <Formik {...config}>
      {(form) => <Form className={className}>{children(form)}</Form>}
    </Formik>
  );
}
