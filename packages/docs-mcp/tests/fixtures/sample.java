package com.example.sample;

import java.util.List;
import java.util.Optional;

/**
 * A sample Java class for testing tree-sitter extraction.
 */
public class UserService {
    private String serviceName;
    private int maxRetries = 3;

    /**
     * Create a new UserService.
     * @param serviceName the name of the service
     */
    public UserService(String serviceName) {
        this.serviceName = serviceName;
    }

    /**
     * Find a user by their ID.
     * @param id the user ID
     * @return the found user, if any
     */
    public Optional<User> findById(long id) {
        return Optional.empty();
    }

    /**
     * Get all users.
     */
    public List<User> getAll() {
        return List.of();
    }

    private void cleanup() {
        // internal cleanup
    }
}

/**
 * Represents a user entity.
 */
class User {
    String name;
    String email;
    int age;

    User(String name, String email) {
        this.name = name;
        this.email = email;
    }

    /** Get the display name. */
    String getDisplayName() {
        return name;
    }
}

/**
 * Interface for data repositories.
 */
interface Repository<T> {
    T findById(long id);
    List<T> findAll();
    void save(T entity);
}

/**
 * Possible user roles.
 */
enum UserRole {
    ADMIN,
    EDITOR,
    VIEWER
}
