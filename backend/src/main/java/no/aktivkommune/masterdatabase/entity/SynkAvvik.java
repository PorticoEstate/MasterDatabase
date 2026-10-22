package no.aktivkommune.masterdatabase.entity;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.annotations.OnDelete;
import org.hibernate.annotations.OnDeleteAction;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;
import java.util.Map;

@Getter
@Setter
@Entity
@Table(name = "synk_avvik")
public class SynkAvvik {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @OnDelete(action = OnDeleteAction.SET_NULL)
    @JoinColumn(name = "kildeuttrekk_id")
    private Kildeuttrekk kildeuttrekk;

    @NotNull
    @Column(name = "kilde", nullable = false, length = Integer.MAX_VALUE)
    private String kilde;

    @NotNull
    @Column(name = "samling", nullable = false, length = Integer.MAX_VALUE)
    private String samling;

    @NotNull
    @Column(name = "avvikstype", nullable = false, length = Integer.MAX_VALUE)
    private String avvikstype;

    @Column(name = "ekstern_id", length = Integer.MAX_VALUE)
    private String eksternId;

    @Column(name = "felt", length = Integer.MAX_VALUE)
    private String felt;

    @NotNull
    @ColumnDefault("'id'")
    @Column(name = "nokkelfelt", nullable = false, length = Integer.MAX_VALUE)
    private String nokkelfelt;

    @Column(name = "detalj", length = Integer.MAX_VALUE)
    private String detalj;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "rapost")
    private Map<String, Object> rapost;

    @NotNull
    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;


}
