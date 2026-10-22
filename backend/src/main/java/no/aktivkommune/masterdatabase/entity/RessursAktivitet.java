package no.aktivkommune.masterdatabase.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;

@Getter
@Setter
@Entity
@Table(name = "ressurs_aktivitet")
public class RessursAktivitet {
    @EmbeddedId
    private RessursAktivitetId id;

    @MapsId("ressursId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @OnDelete(action = OnDeleteAction.CASCADE)
    @JoinColumn(name = "ressurs_id", nullable = false)
    private Ressurs ressurs;

    @MapsId("aktivitetId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @OnDelete(action = OnDeleteAction.CASCADE)
    @JoinColumn(name = "aktivitet_id", nullable = false)
    private Aktivitet aktivitet;


}
