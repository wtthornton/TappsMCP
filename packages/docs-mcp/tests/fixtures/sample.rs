//! A sample Rust module for testing tree-sitter extraction.

use std::fmt;
use std::io::Read;

/// The maximum number of retries.
const MAX_RETRIES: u32 = 3;

/// A user in the system.
pub struct User {
    pub name: String,
    pub email: String,
    age: u32,
}

/// Possible user roles.
pub enum Role {
    Admin,
    Editor,
    Viewer,
}

/// A trait for greeting.
pub trait Greeter {
    /// Return a greeting for the given name.
    fn greet(&self, name: &str) -> String;
}

impl User {
    /// Create a new user.
    pub fn new(name: String, email: String) -> Self {
        User {
            name,
            email,
            age: 0,
        }
    }

    /// Get the display name.
    pub fn display_name(&self) -> &str {
        &self.name
    }
}

impl fmt::Display for User {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "User({}, {})", self.name, self.email)
    }
}

/// Read all bytes from a reader.
pub fn read_all(reader: &mut dyn Read) -> Vec<u8> {
    let mut buf = Vec::new();
    reader.read_to_end(&mut buf).unwrap();
    buf
}

/// An async function example.
pub async fn fetch_data(url: &str) -> String {
    url.to_string()
}
