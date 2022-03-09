plugins {
    val kotlinVersion = "1.6.10"
    kotlin("jvm") version kotlinVersion
    kotlin("plugin.serialization") version kotlinVersion

    id("net.mamoe.mirai-console") version "2.10.0"
}

group = "org.brucechen"
version = "1.0"

repositories {
    maven("https://maven.aliyun.com/repository/public")
    mavenCentral()
}


dependencies {
    implementation("org.xerial:sqlite-jdbc:3.36.0.3")
    implementation("org.java-websocket:Java-WebSocket:1.5.2")
    implementation("com.google.code.gson:gson:2.9.0")
}