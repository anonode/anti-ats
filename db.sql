create database swe;
use swe;
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    fname varchar(50) not null,
    lname varchar(50) not null,
    email VARCHAR(100) NOT NULL,
    password VARCHAR(255) NOT NULL,
    UNIQUE(email),
    UNIQUE(username)
);
