package no.aktivkommune.masterdatabase.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.Immutable;
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;

// ressurs_fasilitet er en visning (avledet fra ressurs_kildekode og godkjent
// mapping), så den kan bare leses.
@Immutable
@Getter
@Setter
@Entity
@Table(name = "ressurs_fasilitet")
public class RessursFasilitet {
    @EmbeddedId
    private RessursFasilitetId id;

    @MapsId("ressursId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @OnDelete(action = OnDeleteAction.CASCADE)
    @JoinColumn(name = "ressurs_id", nullable = false)
    private Ressurs ressurs;

    @MapsId("fasilitetId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @OnDelete(action = OnDeleteAction.CASCADE)
    @JoinColumn(name = "fasilitet_id", nullable = false)
    private Fasilitet fasilitet;


}
