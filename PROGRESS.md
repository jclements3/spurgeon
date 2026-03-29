# MP3 Generation Progress

## Completed (7/50)
- [x] 01_ScriptureExamples
- [x] 02_ConfessionAndPetition
- [x] 03_ConsecrationAndWorship
- [x] 04_Contentment
- [x] 05_TheDeeps
- [x] 07_DivineSupport
- [x] 24_TheValleyOfVision

## Remaining (43/50)
- [ ] 06_Devotion
- [ ] 08_EveningPraise
- [ ] 09_EveningPrayer
- [ ] 10_EveningRenewal
- [ ] 11_GraceActive
- [ ] 12_HeartCorruptions
- [ ] 13_LongingsAfterGod
- [ ] 14_MeetingGod
- [ ] 15_Morning
- [ ] 16_MorningDedication
- [ ] 17_MorningNeeds
- [ ] 18_Openness
- [ ] 19_InPrayer
- [ ] 20_Purification
- [ ] 21_Refuge
- [ ] 22_RestingOnGod
- [ ] 23_SpiritualHelps
- [ ] 25_HelpFromOnHigh
- [ ] 26_ThanksBeUntoGod
- [ ] 27_TheLoveWithoutMeasureOrEnd
- [ ] 28_TheAllPrevailingPlea
- [ ] 29_ToTheKingEternal
- [ ] 30_TheWondersOfCalvary
- [ ] 31_LetAllThePeoplePraiseYou
- [ ] 32_APrayerForHoliness
- [ ] 33_GloriousLiberty
- [ ] 34_TheMusicOfPraise
- [ ] 35_UnderTheBlood
- [ ] 36_OnHolyGround
- [ ] 37_TheWingsOfPrayer
- [ ] 38_BlessTheLordOMySoul
- [ ] 39_ThePeaceOfGod
- [ ] 40_HeEverLives
- [ ] 41_ToBeLikeChrist
- [ ] 42_OhForMoreGrace
- [ ] 43_GodsUnspeakableGift
- [ ] 44_TheGreatSacrifice
- [ ] 45_BoldnessAtTheThroneOfGrace
- [ ] 46_ThePresenceOfGod
- [ ] 47_TheLookOfFaith
- [ ] 48_DeliverUsFromEvil
- [ ] 49_TheWashingOfWaterByTheWord
- [ ] 50_PrayerAnsweredAndUnanswered

## How to resume
```bash
cd ~/projects/spurgeon/scripts
# Generates only files that don't already exist in mp3/
for ssml in ../ssml/*.ssml; do
    base=$(basename "$ssml" .ssml)
    mp3="../mp3/${base}.mp3"
    [ -f "$mp3" ] && continue
    python3 generate_elevenlabs.py sk_... "$ssml" "$mp3"
    sleep 2
done
```

## Stats
- Remaining chars: ~207,000
- ElevenLabs free tier: 10,000 chars/month
- Voice: Daniel (en-GB, deep, calm) — onwK4e9ZLuTAKqWW03F9
- API key: stored in .env
