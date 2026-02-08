"""
Ability System

Single source of truth for card abilities. Declare an ability once
and get BOTH human-readable text AND interceptor implementation.

Example:
    # Old way (text and behavior disconnected):
    SOUL_WARDEN = make_creature(
        name="Soul Warden",
        text="Whenever another creature enters the battlefield, you gain 1 life.",
        setup_interceptors=soul_warden_setup  # Separate function
    )

    # New way (single source of truth):
    SOUL_WARDEN = make_creature(
        name="Soul Warden",
        abilities=[
            TriggeredAbility(
                trigger=ETBTrigger(target=AnotherCreature()),
                effect=GainLife(1)
            )
        ]
    )
    # Auto-generates text: "Whenever another creature enters the battlefield, you gain 1 life."
    # Auto-generates interceptor that implements exactly that behavior
"""

# Base classes
from .base import (
    Ability,
    TriggeredAbility,
    StaticAbility,
    KeywordAbility,
    ActivatedAbility,
    Trigger,
    Effect,
    StaticEffect,
    TargetFilter,
    Condition,
    Cost,
)

# Triggers
from .triggers import (
    ETBTrigger,
    DeathTrigger,
    AttackTrigger,
    BlockTrigger,
    DealsDamageTrigger,
    UpkeepTrigger,
    EndStepTrigger,
    SpellCastTrigger,
    LifeGainTrigger,
    DrawTrigger,
    LeavesPlayTrigger,
)

# Effects
from .effects import (
    GainLife,
    LoseLife,
    DealDamage,
    DrawCards,
    DiscardCards,
    AddCounters,
    RemoveCounters,
    Mill,
    Scry,
    CreateToken,
    Destroy,
    Sacrifice,
    TapEffect,
    UntapEffect,
    CompositeEffect,
)

# Static Effects
from .static import (
    PTBoost,
    KeywordGrant,
    TypeGrant,
    CostReduction,
    CantBlockEffect,
    CantAttackEffect,
)

# Targets and Filters
from .targets import (
    # Trigger targets
    TriggerTarget,
    SelfTarget,
    AnyCreature,
    AnotherCreature,
    CreatureYouControl,
    AnotherCreatureYouControl,
    CreatureWithSubtype,
    NonlandPermanent,
    # Static ability filters
    CreaturesYouControlFilter,
    OtherCreaturesYouControlFilter,
    CreaturesWithSubtypeFilter,
    AllCreaturesFilter,
    OpponentCreaturesFilter,
    # Effect targets
    EffectTarget,
    ControllerTarget,
    EachOpponentTarget,
    TriggeringObjectTarget,
    DamageTarget,
)

# Keywords
from .keywords import (
    PASSIVE_KEYWORDS,
    KEYWORD_REMINDER_TEXT,
    get_keyword_interceptors,
)

__all__ = [
    # Base classes
    'Ability',
    'TriggeredAbility',
    'StaticAbility',
    'KeywordAbility',
    'ActivatedAbility',
    'Trigger',
    'Effect',
    'StaticEffect',
    'TargetFilter',
    'Condition',
    'Cost',

    # Triggers
    'ETBTrigger',
    'DeathTrigger',
    'AttackTrigger',
    'BlockTrigger',
    'DealsDamageTrigger',
    'UpkeepTrigger',
    'EndStepTrigger',
    'SpellCastTrigger',
    'LifeGainTrigger',
    'DrawTrigger',
    'LeavesPlayTrigger',

    # Effects
    'GainLife',
    'LoseLife',
    'DealDamage',
    'DrawCards',
    'DiscardCards',
    'AddCounters',
    'RemoveCounters',
    'Mill',
    'Scry',
    'CreateToken',
    'Destroy',
    'Sacrifice',
    'TapEffect',
    'UntapEffect',
    'CompositeEffect',

    # Static Effects
    'PTBoost',
    'KeywordGrant',
    'TypeGrant',
    'CostReduction',
    'CantBlockEffect',
    'CantAttackEffect',

    # Trigger targets
    'TriggerTarget',
    'SelfTarget',
    'AnyCreature',
    'AnotherCreature',
    'CreatureYouControl',
    'AnotherCreatureYouControl',
    'CreatureWithSubtype',
    'NonlandPermanent',

    # Static ability filters
    'CreaturesYouControlFilter',
    'OtherCreaturesYouControlFilter',
    'CreaturesWithSubtypeFilter',
    'AllCreaturesFilter',
    'OpponentCreaturesFilter',

    # Effect targets
    'EffectTarget',
    'ControllerTarget',
    'EachOpponentTarget',
    'TriggeringObjectTarget',
    'DamageTarget',

    # Keywords
    'PASSIVE_KEYWORDS',
    'KEYWORD_REMINDER_TEXT',
    'get_keyword_interceptors',
]
