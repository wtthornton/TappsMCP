/**
 * A sample TSX component file for testing.
 */

import React from "react";

/** Props for the Button component. */
interface ButtonProps {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}

/** A simple button component. */
export function Button({ label, onClick, disabled }: ButtonProps): JSX.Element {
  return <button onClick={onClick} disabled={disabled}>{label}</button>;
}

export const Greeting = ({ name }: { name: string }) => {
  return <div>Hello, {name}!</div>;
};
