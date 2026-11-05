package no.aktivkommune.masterdatabase;

import org.springframework.boot.SpringApplication;

public class TestMasterdatabaseApplication {

	public static void main(String[] args) {
		SpringApplication.from(MasterdatabaseApplication::main).with(TestcontainersConfiguration.class).run(args);
	}

}
