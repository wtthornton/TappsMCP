/**
 * A sample TypeScript module for testing tree-sitter extraction.
 */

import { EventEmitter } from "events";
import type { Config } from "./config";

/** Maximum retry count. */
const MAX_RETRIES: number = 3;

const API_URL = "https://api.example.com";

/** Greet a user by name. */
export function greet(name: string): string {
  return `Hello, ${name}!`;
}

async function fetchData(url: string, timeout?: number): Promise<Response> {
  return fetch(url);
}

/** Add two numbers together. */
export const add = (a: number, b: number): number => {
  return a + b;
};

const processItems = async (items: string[]): Promise<void> => {
  for (const item of items) {
    console.log(item);
  }
};

/** Represents a user in the system. */
export class User extends EventEmitter {
  name: string;
  age: number;

  constructor(name: string, age: number) {
    super();
    this.name = name;
    this.age = age;
  }

  /** Get the user's display name. */
  getDisplayName(): string {
    return this.name;
  }

  async save(): Promise<void> {
    // persist user
  }
}

/** Configuration shape for the app. */
interface AppConfig {
  host: string;
  port: number;
  debug: boolean;
  getUrl(): string;
}

/** Possible log levels. */
type LogLevel = "debug" | "info" | "warn" | "error";
