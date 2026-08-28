from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BrawlerSpec:
    character_id: int
    unlock_card_id: int
    code_name: str


# Extracted from the v68.250 characters.csv and cards.csv shipped with the
# supported APK.  Character ids 33, 55 and 88 are disabled/non-Hero rows.
BRAWLERS: tuple[BrawlerSpec, ...] = (
    BrawlerSpec(0, 0, "shelly"), BrawlerSpec(1, 4, "colt"),
    BrawlerSpec(2, 8, "bull"), BrawlerSpec(3, 12, "brock"),
    BrawlerSpec(4, 16, "rico"), BrawlerSpec(5, 20, "spike"),
    BrawlerSpec(6, 24, "barley"), BrawlerSpec(7, 28, "jessie"),
    BrawlerSpec(8, 32, "nita"), BrawlerSpec(9, 36, "dynamike"),
    BrawlerSpec(10, 40, "el_primo"), BrawlerSpec(11, 44, "mortis"),
    BrawlerSpec(12, 48, "crow"), BrawlerSpec(13, 52, "poco"),
    BrawlerSpec(14, 56, "bo"), BrawlerSpec(15, 60, "piper"),
    BrawlerSpec(16, 64, "pam"), BrawlerSpec(17, 68, "tara"),
    BrawlerSpec(18, 72, "darryl"), BrawlerSpec(19, 95, "penny"),
    BrawlerSpec(20, 100, "frank"), BrawlerSpec(21, 105, "gene"),
    BrawlerSpec(22, 110, "tick"), BrawlerSpec(23, 115, "leon"),
    BrawlerSpec(24, 120, "rosa"), BrawlerSpec(25, 125, "carl"),
    BrawlerSpec(26, 130, "bibi"), BrawlerSpec(27, 177, "8_bit"),
    BrawlerSpec(28, 182, "sandy"), BrawlerSpec(29, 188, "bea"),
    BrawlerSpec(30, 194, "emz"), BrawlerSpec(31, 200, "mr_p"),
    BrawlerSpec(32, 206, "max"), BrawlerSpec(34, 218, "jacky"),
    BrawlerSpec(35, 224, "gale"), BrawlerSpec(36, 230, "nani"),
    BrawlerSpec(37, 236, "sprout"), BrawlerSpec(38, 279, "surge"),
    BrawlerSpec(39, 296, "colette"), BrawlerSpec(40, 303, "amber"),
    BrawlerSpec(41, 320, "lou"), BrawlerSpec(42, 327, "byron"),
    BrawlerSpec(43, 334, "edgar"), BrawlerSpec(44, 341, "ruffs"),
    BrawlerSpec(45, 358, "stu"), BrawlerSpec(46, 365, "belle"),
    BrawlerSpec(47, 372, "squeak"), BrawlerSpec(48, 379, "grom"),
    BrawlerSpec(49, 386, "buzz"), BrawlerSpec(50, 393, "griff"),
    BrawlerSpec(51, 410, "ash"), BrawlerSpec(52, 417, "meg"),
    BrawlerSpec(53, 427, "lola"), BrawlerSpec(54, 434, "fang"),
    BrawlerSpec(56, 448, "eve"), BrawlerSpec(57, 466, "janet"),
    BrawlerSpec(58, 474, "bonnie"), BrawlerSpec(59, 491, "otis"),
    BrawlerSpec(60, 499, "sam"), BrawlerSpec(61, 507, "gus"),
    BrawlerSpec(62, 515, "buster"), BrawlerSpec(63, 523, "chester"),
    BrawlerSpec(64, 531, "gray"), BrawlerSpec(65, 539, "mandy"),
    BrawlerSpec(66, 547, "r_t"), BrawlerSpec(67, 557, "willow"),
    BrawlerSpec(68, 565, "maisie"), BrawlerSpec(69, 573, "hank"),
    BrawlerSpec(70, 581, "cordelius"), BrawlerSpec(71, 589, "doug"),
    BrawlerSpec(72, 597, "pearl"), BrawlerSpec(73, 605, "chuck"),
    BrawlerSpec(74, 619, "charlie"), BrawlerSpec(75, 633, "mico"),
    BrawlerSpec(76, 642, "kit"), BrawlerSpec(77, 655, "larry_lawrie"),
    BrawlerSpec(78, 663, "melodie"), BrawlerSpec(79, 671, "angelo"),
    BrawlerSpec(80, 730, "draco"), BrawlerSpec(81, 748, "lily"),
    BrawlerSpec(82, 760, "berry"), BrawlerSpec(83, 768, "clancy"),
    BrawlerSpec(84, 800, "moe"), BrawlerSpec(85, 811, "kenji"),
    BrawlerSpec(86, 828, "shade"), BrawlerSpec(87, 844, "juju"),
    BrawlerSpec(89, 871, "meeple"), BrawlerSpec(90, 879, "ollie"),
    BrawlerSpec(91, 901, "lumi"), BrawlerSpec(92, 911, "finx"),
    BrawlerSpec(93, 925, "jae_yong"), BrawlerSpec(94, 934, "kaze"),
    BrawlerSpec(95, 985, "alli"), BrawlerSpec(96, 994, "trunk"),
    BrawlerSpec(97, 1035, "mina"), BrawlerSpec(98, 1043, "ziggy"),
    BrawlerSpec(99, 1056, "pierce"), BrawlerSpec(100, 1064, "gigi"),
    BrawlerSpec(101, 1177, "nori"), BrawlerSpec(102, 1185, "najia"),
    BrawlerSpec(103, 1212, "glowbert"), BrawlerSpec(104, 1241, "sirius"),
    BrawlerSpec(105, 1249, "stella"), BrawlerSpec(106, 1275, "bolt"),
    BrawlerSpec(107, 1291, "katana_kid"), BrawlerSpec(108, 1314, "wendy"),
)

BRAWLER_BY_ID = {brawler.character_id: brawler for brawler in BRAWLERS}

# Counts are extracted from the v68.250 csv_logic tables shipped in the APK.
# Static-data instance ids in this APK use 1-based RowIDs; the second CSV line is
# a type declaration and is not an item. Keeping exact ranges here prevents
# arbitrary client-supplied DataReferences from entering persisted profiles.
PLAYER_THUMBNAIL_IDS = frozenset(range(1, 1326))
PLAYER_FRAME_IDS = frozenset(range(1, 41))
PLAYER_TITLE_IDS = frozenset(range(1, 261))
SKIN_IDS = frozenset(range(1, 1979))
CARD_IDS = frozenset(range(1, 1439))
EMOTE_IDS = frozenset(range(1, 3218))
SPRAY_IDS = frozenset(range(1, 743))
NAME_COLOR_IDS = frozenset(range(1, 13))
ALLIANCE_BADGE_IDS = frozenset(range(1, 61))
REGION_IDS = frozenset(range(1, 267))
VANITY_IDS = {
    28: PLAYER_THUMBNAIL_IDS,
    52: CARD_IDS,
    68: SPRAY_IDS,
    76: PLAYER_TITLE_IDS,
}
