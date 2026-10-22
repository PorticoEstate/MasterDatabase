package no.aktivkommune.masterdatabase.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import jakarta.validation.constraints.NotNull;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

import java.io.Serial;
import java.io.Serializable;

@Getter
@Setter
@EqualsAndHashCode
@Embeddable
public class RessursAktivitetId implements Serializable {
    @Serial
    private static final long serialVersionUID = -824647241905997863L;
    @NotNull
    @Column(name = "ressurs_id", nullable = false)
    private Long ressursId;

    @NotNull
    @Column(name = "aktivitet_id", nullable = false)
    private Long aktivitetId;


}
