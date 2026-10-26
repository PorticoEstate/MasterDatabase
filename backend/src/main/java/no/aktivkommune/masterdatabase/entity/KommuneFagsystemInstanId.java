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
public class KommuneFagsystemInstanId implements Serializable {
    @Serial
    private static final long serialVersionUID = 7758635849203335107L;
    @NotNull
    @Column(name = "kommune_id", nullable = false)
    private Long kommuneId;

    @NotNull
    @Column(name = "fagsystem_instans_id", nullable = false)
    private Long fagsystemInstansId;


}
