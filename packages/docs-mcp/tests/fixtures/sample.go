// Package sample provides example types and functions for testing.
package sample

import (
	"fmt"
	"io"
)

// MaxSize is the maximum allowed size.
const MaxSize = 1024

// DefaultName is the default name used.
var DefaultName = "world"

// User represents a user in the system.
type User struct {
	Name  string
	Email string
	Age   int
}

// Greeter defines the greeting interface.
type Greeter interface {
	// Greet returns a greeting string.
	Greet(name string) string
	// SetLanguage sets the greeting language.
	SetLanguage(lang string)
}

// NewUser creates a new User with the given name.
func NewUser(name string, email string) *User {
	return &User{Name: name, Email: email}
}

// String returns a string representation of the User.
func (u *User) String() string {
	return fmt.Sprintf("User(%s, %s)", u.Name, u.Email)
}

// ReadAll reads all data from a reader.
func ReadAll(r io.Reader) ([]byte, error) {
	return io.ReadAll(r)
}
