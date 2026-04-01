from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `chat_feedback` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `helpful` BOOL NOT NULL,
    `feedback_type` VARCHAR(50),
    `comment` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `assistant_message_id` BIGINT NOT NULL,
    `session_id` BIGINT NOT NULL,
    `user_id` BIGINT NOT NULL,
    CONSTRAINT `fk_chat_fee_chat_mes_e122cd01` FOREIGN KEY (`assistant_message_id`) REFERENCES `chat_messages` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_chat_fee_chat_ses_2d731e1c` FOREIGN KEY (`session_id`) REFERENCES `chat_sessions` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_chat_fee_users_36ea5b2e` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    KEY `idx_chat_feedba_session_cf3ce3` (`session_id`, `created_at`),
    KEY `idx_chat_feedba_assista_6b4bc6` (`assistant_message_id`, `created_at`),
    KEY `idx_chat_feedba_user_id_815aa2` (`user_id`, `created_at`)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `chat_session_memory` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `recent_topic` VARCHAR(50),
    `recent_drug_name` VARCHAR(255),
    `recent_external_drug_name` VARCHAR(255),
    `recent_profile_focus` VARCHAR(255),
    `recent_hospital_focus` VARCHAR(100),
    `pending_clarification` VARCHAR(100),
    `clarification_question` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `session_id` BIGINT NOT NULL UNIQUE,
    CONSTRAINT `fk_chat_ses_chat_ses_eca5e93c` FOREIGN KEY (`session_id`) REFERENCES `chat_sessions` (`id`) ON DELETE CASCADE,
    KEY `idx_chat_sessio_recent__8e6b7f` (`recent_topic`, `updated_at`)
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `chat_feedback`;
        DROP TABLE IF EXISTS `chat_session_memory`;"""


MODELS_STATE = (
    "eJztXW1znDjW/Ssuf8pUeafsdnfi5JtjOxnP+mUqcfbZ2mSKwqDuZkxDDy9OvFv574/Eqx"
    "BCRkADwremKpOArhqOhHTv0dHV//Y3rols/9dT5FnGev/d3v/2HX2D8F+YOwd7+/p2m18n"
    "FwL93o6K6nmZez/wdCPAV5e67SN8yUS+4VnbwHIdfNUJbZtcdA1c0HJW+aXQsf4OkRa4Kx"
    "SskYdvfP0TX7YcE/1AfvrP7YO2tJBtFh7VMslvR9e14GkbXbt0gg9RQfJr95rh2uHGyQtv"
    "n4K162SlLScgV1fIQZ4eIFJ94IXk8cnTJe+ZvlH8pHmR+BEpGxMt9dAOqNetiYHhOgQ//D"
    "R+9IIr8iv/mB3N38xPjl/PT3CR6EmyK29+xq+Xv3tsGCFwc7f/M7qvB3pcIoIxx+0ReT55"
    "pBJ4Z2vd46NHmTAQ4gdnIUwBE2GYXshBzDtORyhu9B+ajZxVQDr4bLEQYPav009nv51+eo"
    "VL/ULexsWdOe7jN8mtWXyPAJsDST4NCRCT4moCeHR4WANAXKoSwOheEUD8iwGKv8EiiL9/"
    "vr3hg0iZMEB+cfALfjUtIzjYsy0/+HOcsApQJG9NHnrj+3/bNHivrk//zeJ6dnX7PkLB9Y"
    "OVF9USVfAeY0yGzOUD9fGTC/e68fBd90ytdMeduVVly7c2sw17RXf0VYQVeWPyfukkEgbr"
    "U8NwQyfgzjHUbfFEgwtqelzS736++bq/9dxHy0TRh5j+XQt9/AeeNv5sMx+9t1YTmpLezm"
    "bHx29mh8evTxbzN28WJ4fZ3FS+JZqk3l9+JPNUoUc/P3HRzVR30C00rZIj76zOwDurHndn"
    "pWG31MUb4EnbNsI16aHDTWi1cD0SAHtURtbwEHljTefMaef4TmBtUMW8VrBkEDUT01/Tv4"
    "y03+J3MG8d+ylpXgG+d5fXF5/vTq//KMx356d3F+TOLLr6xFx99ZppiqySvf+7vPttj/xz"
    "7z+3NxfstJiVu/vPPnkmPJ+4muN+13STGivTqykwhYat/FJEA3z1J8IZ5UfShL0N9CUfpQ"
    "h2GekProeslfNP9BShfYmfW3cMxEE38S++JNWMD+WfaU9Jr+a90NO/Z64F3YHw6+GXQkE8"
    "PJ9+Pjs9v9j/OYxfd6Z7aGXhmPAPPbCwM35lOQ88B49bTujpGamFto1NNBvb7MTny38q7W"
    "7JT4LDNxqHD3/hQejLuCe5hZrO3nEdp+S42ic5BpfkpbgkHnp0Hxo1bNGyg4bt35dXpB3T"
    "1xY2ZHEmkvYyuebgb5bnGSoATpwLWaiLdoCxhE9fdrdevHfP/XD5fj6n83YA4R95TeqiWP"
    "wmRxUmrfXgA0ImqW2fFx7R9w+EYREuqS3portccP267yOfLPclmFJ+IC75dV/HN0nXCrQN"
    "LoffvaIc1avpWxBODRVOrZG9XYY2B2XXtZHu8GGmrBis77HZqAcPLnS3t1cFz/D9JQPkzZ"
    "fr9xefXh1FLiEuZAUVbkT6RcaAlFCtjlJLhkoy6Is6seqiOlZdcNaDNxvu1HaHflR5v7mJ"
    "IiCKQpeLf9+JF4CzyOXq9uZjWpxdFQYC4EUQAFXzcP0ZtKoGiGxE0WPRO6qPdtEOMBZhDO"
    "ttXaMriM2TjtlBRElCms95bePDu25UWfxWnw/KSyNpR2Be57WpC2bVNPM8rMAVjXwlmOqi"
    "FQwH1YOfITiSzrGD1V4JggPYiaHYCc+1pYLotLyaC73dq/oqxdSi4LlKTD1aFCF6hui5k+"
    "gZojiIM4b36+rEGdWuXZmK5oil3iemH/75Cdl6wN/GVbEkpQ6wP3ft5qbdrcLNpXrjM25u"
    "0uR9uLkVK3Bkca64bAoe8Bg8YNJjZDzgtLwiCx+gdARXrZGrNqBca4CvBPj2SaAL+1s6YD"
    "WH1r0Npg5oI3v7fHG3d/Pl6goih3qRA93JaA66HRhKrtzIRVE0bBvXe6oG7dZBdy7+ox50"
    "SSx1nVWqzFf6s3lgmbytOLzMIakXZGp5w+w41PSQQYajwN1aBvm5cGtCRDl4RMm2Su21Fc"
    "ZOyQize31iAovphSstuiYPacFWSVh3kkopQQf9CJDn6HYriPmVANYM1lvPXVo20pauIbfH"
    "tsoeEGYQXrv+1gpwR2wKcbkCJTHeSe6wLXJM/AiaYeuetbSMzK+si3FlBYBxxqjS0Gj4xX"
    "w+yAKFQWUNiqAMegMgsbvJIJQHRJINW7SEhh20YUuM0Zh0JNMJakvsuYy+tYbiJCWk+tGb"
    "7LpddqY2aaeaIMvTPD4rWbYWUFj40k6SPq08N9xqRvIA0f8jNUTx+qNu42Zj00CxpSxfw0"
    "9mPUb/8F0v0FyPJJoEumswusuQFFAYbQQUg0uIu+e34o4vAWBmAAjGCJqWv7X1J2nqirVT"
    "E8+dBKH0k5UQrY48GTMIN7nhJjVvlbCtdl0LRv1JPw5bz08tz1SgpnJ68mdmdFEyjYJdj+"
    "k0sul+xOk0gPqYRIQM1MdEG7ZEfeTxkGQS+ZKhmu5ON3v4BELBYsDZds8M/t9HUuE4oa3L"
    "YZT6zqj2Q2cYV/AeWQOIyQ8tesvdbxEBqmIoqkL0adcZOLsbNXeO9473PceYyAbcRSs15x"
    "8It1ULtyFshLARoot9CBtfUMNmuvia67nF5Zy2OzESV2l87TvIRvZz1wijdKmc8CS7dyCK"
    "TsykVB/b16v3qEfppbe2q5v4wv2TBqmmRxbeRMrg0OPkmhZkRaZs1HTIF7Uc8oXAIV+UHX"
    "LXs1YWkbMTfGTDHK6xIs55D0LtqMtFOMj209RISSy7z70QYeJb/+UFNoJxtWAGG/QFG/SN"
    "NTIe/HAj01FpGyX76U6+eThUrv3nDjH3JEKzcswdr6Q0adiiJRwqN/ChcnDEWQ9Jc/gRaH"
    "2wKyoA1CWS6cBxaNLHoYn6cAc4TiAvEf+7bJ6ecxVaranMj6QOtXAt8hiGp/3l3rdE4dbw"
    "fnfvFYNhp5SuF67O9EC33dU+j9Wlbh8IiV2SLMGgSu6W240eEwja4XKNLk1fswK00Xz0t0"
    "wwXDLshFnoV4SyE+GELDWrtvZkJ9QMHuTCJR5zQo/niAj6JGMHZFc2jjo4qDStdMGurpqH"
    "MVMEz77VPHjydvDzSCFL2wCskALjJZGLIOiZRMM2F/Sk5MQGmS3DwISruUbmmIfM/iPBS2"
    "fpnunGGu1XxIJ5gYNno0ELl8UhYVp4twEh+rG1cI/M5D1Z8j4t2RsN0SJEi9OJFsvdWwJV"
    "rrEi3iSEkQoiipYkh5/B6aTVkQ5towiSfUc6phufhovnWRlkGTMAlwvu1kMG9lrTo7bqgs"
    "uYAbj8jUxOgIgzKIsuawfw8tOyWCbS8ACKDDnejrUDePnwBvg+HkE3OBxxpTIXlC0VgbgP"
    "JyGP4EqIiumdoiVoxwbWjgEBOwmeDgjYiTYsELAjJWBD79RGHn93ZXrvQEi7hp6mk2LDb6"
    "+kukpFiehBs41QNnpEdkLd4reI9p4QQ2BtB2Ntiw1U18UtWqmpTuk+sWvcvSVgzAzURLD7"
    "PUP3um/52l++XF6ZopUiwVbf8ewmP2uyLq6UCYAKuXogVw8EIK32DdIun5RXx1rC5ifRlj"
    "PY1tcfxnnkI49zbgtYi7D2CNGAsWqDeXUdkFGi/j7KbBwugy+9A/A89M7SqsbX0+vuAmRn"
    "puc3U8Je1FZ7UakPuDsI6zGUCqCYD2vPI8kZEvtGdDycLwto9XxRAPbzxd3ezZerq6FyiW"
    "eDKJ9NzgZYMZsc5wAanE3OU+iwd/BPrVbIywhHyN83BuqYbZW6rCdrpyb52T19DEmn2hPI"
    "yPNcTzplftFKEa6zBwF6jEsD5rhkqAim/YvMdK8Z11m0BDnUwHKopeVY/rpRSzKm0JSgbI"
    "P1h12sPwAvvnuuNvHtW+S7q6oBeFrId9cTx1jqgh0AWTPh3XgZsarvUpoPY7RnLTWmtGZS"
    "nR66U4npxY+Iw0PmNSoyYrz7ByJyEKUlMzFwfwRhRPwl+QBBIzoo0QdZy1rve0q24wb4i5"
    "JBkjFThEXp41AOD+G3cYwnaUjLloAqtb4fTbfy/ZQ1BEzzA8qcpWWixDlk6ARkWBvdrmAT"
    "CoYsmxBb/prUMEpwBVieX5xdXp9evVoczBk9aIryHM6TeCm8DOXkSflxRTvgZUATOioSJu"
    "meHXAHKuYzP2Dog+LHCjK5HVBYw0iQ4iMHODRDdhZBNb+QH3kwim2s8d1H5PnkN+NtqslR"
    "pmLJEnATg3ETItHMhRNuSoPE4AKa/Y8XNxefTu8ubz7ul9Cnbr7by//+zTnHvte7PfLnN+"
    "fD6eXVxfm7vfj/+/Vaqxjp1BGLzKq1IrOSd55+NaWGqOzqlEV/fsVR6/4+O5q/mZ8cv55n"
    "3Ty7IurdnH1urhOQkYUfa1dra1g7RULtvqU1KUz8zcS/f769EcNbsZ34i4Pf+6tpGcHBnm"
    "35wZ+qgU3eXAw2i+tBMeIjFZTA1j20svAXrfnhZqN7nCSQAsR5xgB7DdhNyzds3drIpTAt"
    "WvU48X0L743lyd63UDcOD7+Fxps3c3xpbhr4z9nb+R65tDjB/zgxjOgfb3Gp+/vjk7gsub"
    "SYE5NZfN8gd3QDkbpe62/JpZOjRfQrc2JysojKkhpnaP5rebYdE0+41C079JC0dpW1U2Q6"
    "6EG9miLTQL/KMVUE196nWWBlp8nKQh64STRs6YjF9LNrqs/j24M6T0C+MyRSfawZQ6DfYY"
    "lj6FQMGRLa0nM3DfIwcCuA4QPEvT2Je9MxtQP8zqmq1AWQmWSeR5DxADoAUnlxNN8pqpBG"
    "iwbUDsCsewb4eNGsmCRaKM3pGvs8Z308GBeZEYRMAlkXKHxI6lJrENypAL+IS9XSOA3cM0"
    "vk2pIuu9ul8vgHy8vdsMQ91BI3kdbihyyBXO1kZwZq+dXdLa0CKTkF7qpMStKDU/0Rh7aC"
    "+F4U3zdiBNvSgJNGVxDIr1InsieHf0TuF+vx01/o8wFov1HniGGrijUHloT+5vpbK9Dtz8"
    "YamWEEYskFLpUResHrpLTmJ8XriUYjxYF5ROQB5mGkKHhjxCIB/A/zaG5kIgR0NN9nmkbK"
    "+JuD/wsNc0GuHp0Ye2efvpwTpQM6JuqEt7He4ZgoHU4WRLygm6+josdH7745/4ikDfekro"
    "VOdA7m68VJKoAgmojCz0d/J7ffGoevEvrrl6QS+hnx/8jv6frbV4EV2Cgpk78UuXmyeJWB"
    "S5ooq0hfxG/yynaNKA5M77w+JL+9eGPmvzczjVdpyxDfKf0lfTGPHuDkFdUu6c3Z4TxWgp"
    "B6Dk0zRgO/++LkJBaEJK/IkCuR9/F8JAPxymB5AUlnk5GwZAZqbhjezdnf1JOVoBQc+1s0"
    "A9EKV7RSGPFkemrJUBGAe+iw6TQhAydtoySSO1EC0jOpLH/B2qrJYCjCWKSvDenkqj+X6X"
    "JRIJCbRMOCQG542hGkW6AiUktFBBqYdhqYYYhJPJDoD+jKXe1zGMn85oGIirSiYprtrvrf"
    "uF7w7v/kn8BcLAMs2GAb08cVxY2L1BmRR1griCOfvNOgIWk7aMSBGxHOV+GyU1LnqzhuIL"
    "WRMi2vCLsHuyeBQ4CzBkbtccEZvENg7SHD9cwWrFhFBUCLCUBPwwBpsBlDALkOyGSebI40"
    "ZQ1wAw3ZEw3pU+q5lvhdI5PW4o2uu9aFkBn7auzBK3zD3SJ5N/K4vj6a1PhWA1I4pbu7U7"
    "qLfhOsNFT6kiNbani0gkjcdOby8+MyJQ7Eiw5p2SjP1+5XHmDdYKh1A9n8b63yvvWPcQ+H"
    "Fv/YWh7yG3BqRUvg6wfm6/HQ3khd5cO62ViaEPht4LeB3waqZCCqZBjXn2ZSOH4/Q7RUO/"
    "0kTJTb79ip1ig52oKjMgJV0ZDHXXiBRqY9/oRaqWOgrESTqWoeEZkLWf/fMaUBom0mDg+o"
    "YNqrYMCtnahbC3t6JtGwpT09EK6AHEd1rCE03NUqOqxWtlmtrA6yqbiwuGmGGRgkUo4WNu"
    "mM1RMXJ18l839LFOQVBiPqZ8zy9oY8gdcSkE9JNWr1ip5IqKiLiImotBfVI6O0rAvvmJFi"
    "tDyWr+Hfsh5RzEpFkhR3iQP3J6Ckhkz3lDdDCem76q1RRbOqiGm80dIz0VEhBOKGPznDcP"
    "ILL+Qh0U5hsMRQ+QSy7wg9yBA4rJ0im3F60ArkI0p5jHBdG+lOxSBB2zFw3mPDXfXYbADp"
    "use+v729KoTy7y/Z7Utfrt9fYIAjeHEhK6iIA4EcmwSHUibHBt2O8FJD+8EU3iOKGA4kJN"
    "4QltbHFSKx/R4isRs3sJZWkuiQE4YV7h+IYjCHKtlH+EVpq+mTQEjsRd0iEx7kGhk2BCMY"
    "SQQEaXk113MXdQKBRXUcsCiFAT1nLB46lNpJ1tJ71+TF/5WZIdLyiiDYd2aIrf5ku3hg/c"
    "uXSwDN2gG8XHh9srLRIDFTbgba8oG15anfIdmElBk0IWwPAKpoYtsDppxIgRevN8jEUjAE"
    "kOE8tHFQnXCsF6p5rBdnqO0AuPrar/Ewdyx0AulX1QHcOV/ZEj8lqU8WQGZ2GFVOBZop/Y"
    "wCcshtPOQIGNWs3EFdZlXzaRNIsjBFwjRZ+Kn++MWr/2Vr0AAURtWN5Ue78G3kcWYmIbis"
    "KSBbQLZ0EmbTTiyuCFAvoO4anma6jqxMiDYDRAuIxif+EgaEs2ogBJWxBFyBUnsJlBpsTZ"
    "xEw5Z0N0Axde34j5di2nVw1RnBNEx8f2t4v7v3+5yIPrlzIIrhibP1l3s/bKYUXGG4SW6B"
    "IGrINCmQ5KJlkgsPBd4TRijkkcuC1aWCVX+z02HrPjs7mr+Znxy/nmddNbsi6qFlHxx5nu"
    "tpsok8i1aK6Hb6yOcZ4bJBvo9njTKg1VKokqEimPathYKQcRKRBYSME23YUshIO5lSfiRj"
    "CKEjHEo9qvA87Z8dhOjnVFXjQ7tuoM58sONUg4wYv3ZJYumc8hGdgGfEDTJb7pC7SOtSLk"
    "OQ3DY5KpLETRJgCKtxu3XQnYv/eB69W8P7pH+/S2obq+/Oh06OCktfk0+HUSCIKbEUfJCz"
    "TJfuqv7AqqNj2kYVygsiYwigOomMk7UCad++aNeNbz+dIark2cssI5Uap9wyqZdQ04PNF4"
    "3G1iR13ddid6vhvrZafks9fo7DQQUD1d5G4myDo6H2VyxyNEzL39r6kxb9uwS1IAMZY6cI"
    "E9/D6ga4GBN1MYB8n0TDlsh39zvGWmuk2iqZAjk8us2X7CQznXldwLvnHbMD4lj9/Zel77"
    "Q5cWzoHlpZj7gm23IeWjLHZ2lliTt+hatUC+mi67PWA81Hvp+mM2uBDK7qc1zTKB3JWnik"
    "iz0tsVBz5auIROjFG8DaQhF6p+k+MoWhMNbIaDt2YCjOSDUKQwGLcCVIor1QLaH4SOpQGI"
    "PSRsaWePyW1KdmrtwCNIPktx0vGI+4WaMd/kRk2xqRtLYzV+nPp3TKbHNMlE0wXQCklGW3"
    "OSBsal81/VJ6Y01zLJqvxowEBuo8rJZQqHpCWBEOz11aNtLWlh+4ntV27Egw+SOu9beo0i"
    "eF4ek/nfqYkBAt7/JpJsm13ZokU99sXtsNmBUZlqqgTL7B6i5WX1dX/P7UmqyarXNfo+Li"
    "MXdwfna1O5sOet1yypyEZnrhSsNuho49/WjnaXbRcpYuvoO9MtiROuyOVDf0DKQ13rrBt4"
    "fknYL1owSyplovrjkA/jzgBZ6uKey8SgB8AfiDSnOGWJPe/ZEWpsvfciwA01Vsr3EPKHpu"
    "GEiBmBkoieFOVGKOG/AC7Gp1f2agCIZ9K/vh4M8dpJ5znaXlbZqJGRlbOJoDjuYA+SLoUq"
    "FhayeFYDig8rwmSgxRNoZgSxRslbk1ebxL9gA5pOMYkywYkklIJ5OoGpE7wPAcV3eW1za6"
    "YaF2TpPyXFPjnBZmxOwIz0tc4Vlan9qIlmYT6aNbQH/LXce3I6d3AEjG0+FAVFgFxotXzp"
    "WVHp1vSE81CdWL9ZRq4fkF+0Q0AdvUp7vYfm95wVp7QjpHaFSJctFIrViss9TFPvohs1ST"
    "FFdkkYFZ7KqzTjOrXqaZlVZp1tgBXQeaseEwa8iwNrrNR7Fgx/JqseGvSQWjxFWA4/nF2e"
    "X16dWr1wczZv0gRXhegvF7DMcDJ2gSwliwAxjvN5YkgIkFQIdrN60K/X/1mmvRSpExse+F"
    "V93G0c+KKxevRrZgBMBygQWJQMeAEmGv9pcfh211QS0YAbBV2gt/4z7IH7tK2zXTXowK3A"
    "6lFxiadBus9V/ECy+fAZa1BngZbaWBY6AV0sjqNn/dvFJdyViK1s1Vg5gse7Pz++NK822E"
    "trhLhZ6vbZGHX51zxqfQExXUMk3v9PiA7YXV3ikBx7BW2lY3HmJoviP00ABhfiXTBHguCb"
    "BuG+7atbV7Nwhs1ApmUVUANkEIP6lnWD7SNpYTBkgwalSyd89V80L5PDy1x4uADXwCyrBH"
    "passDz+MQxBD00BEV7QEmevAMte0Oe6fNM/l7aQV7PUomyoS8O2aBwft8CQkpqAdnmjDlr"
    "XD+VDWKOkq314tl+sFy1mnIwoQiFmZPlpGfVeJbscj4zpgdYPcz1ZaNyhK9lIpIZbM99JC"
    "QDyWnC/SZ9F1qJ1K8yk9K6GiEi/VVlIlKaBiIxBUqTp2HuxVC6pwi7qedIRUtILgKIXS4q"
    "0pCmHki0dfKoS+o2/9tRtIr86WDFVJdtH3Ei1E8JMI9MoRfDwkNwrySqYQ3ykS300JY9iu"
    "uKvtivn3DbExZ7TrICzuMLrDkKN/IS/PLs2L7EqFDoRRHSmuPVLle8lrSX6V/A76sbXwPE"
    "ccB0hTOViglzVH3eAkM1DFlS4GJ8d1gpPj6uDkuBScBO4DkgrvMoNuENx5P919trN4DGoU"
    "fjCmsL4+8Po6NapLtmTREhoS8oEBI9AVI1AKoobxYj+hJX6P9V00AXIc2MJ9oe/qxSW1aC"
    "7tw22lAgNwXMfguEYtr611fy3te2VWarqwO0naO6J5e2R0+4iG91oTt4cecSdvMnEXLcED"
    "Aw8MPLCdqCqHOOf8pS4SwCHnSHwEVY3jzXcbEyQHnnHjgfwwNFEsQJ281uupTPEvR4EAOY"
    "AJ96Eg9JkbECEMFiEQjGRig6S8mlFB98S2sdYdB9kyEFImSkqXugcxHwmknXHKEHzxgX3x"
    "fGiv+ynkFvAlQDgz5XAGlE89nLSXJIuVP12vaAgSvjogk2GkOdKUNcANar6e1Hw+lU66JX"
    "5yyanHK+ljxr4ahw4UvuFukbwbuZteH01qfGtx5IDjBkXdITPSSiRTv6GqUgrinSZT/+RG"
    "b1sm1ZLtWQJCzYVs6VMmxgzc5FKsTlJeRb3i2xph7NvKKPZt6VxWycOWuz1kuV/ouqcA6M"
    "eSAJExU5JP2YloAyiViVIqkHdnEg2b+Xg1tZeMRCDzw5q7xmTZOnX4xtfQg/jF0Uo+xy9O"
    "V/ir/WLSKOAXT9cvRhvdklruzAxUdO/mddy7ebV7V87sSmS1eOrZ6r7/3fU4vVWwqyyxaS"
    "fNHdrJO5qd1NkcNTup3hxF7o0p5OjdT+48eQh+Y5MnASMIXjjhpkTlFdDMrQfGc//69Ori"
    "3R7585vz4SL+V/z//QY4v64BM+sn5Si/Lp09RM5S46d9r0yVH5+/1lGa/HGJxjl58uPd1r"
    "i/3Vd1xoqRsdv9tv3OMd1/zY5lPEiPiJSNkvPKog6Mi2oYFyUYLV8jWaYeOTg+lyU8t+sx"
    "SXjWS0ecIxzYmEkE7cDGTLRhm7MxuJI1HvcMN3TaHgd+iqs6jWsaZ3NXcjKFoU730ArPAp"
    "5mW85DS0jO0soS3cYVrlJlbNZ6oC0RMkmvagsNrutDUpXqkPjI99uv9RNEPsc1KQxIuLVd"
    "3cQTA64v3KDWo8p5Uo3CkOAqVivkEUxCTzPWqPXHcx56Z6SaUTr49b6bxC9chZbZdiXgI6"
    "lDXSgiCLoaViMspjCuJv0jPcxRSzVaLfH5LalPSRUgs/3GcD0y0OL7+kNbXC6jSq7clbqA"
    "DCe7G+tHRCOCnZQgwDV2iMxnqkZFEXK/O9GyTuSdt4RGSW02I2KKD9FgDkXoBpfkVAZ1xx"
    "f+URHc49+bw0MdWqEmSuX0Vc2hYZNmKftZPVpGF3KX86gihZF44dqfwn6MTqZjAoSi07CU"
    "EKrGXqoUtvQ0pi4n7BGNtQ0kYcmwUSEMywcVsTxMo4ax/jIS5qtykG5kuEza+Etaut5Gan"
    "GfslFyZbr7PQLbMPWLpIAsWKkpfVrUSq29EKTWXpRTa8NCPyz0w3pw3rEgMd9Y9vtDYj40"
    "6sR8WfhY4RI/v4+4GMh26w5/zfpPdNzkn7CJYiRusO77+PttNDsypjA9jmx6JF+a9PRIGc"
    "H0KMo+BM4HOB8jdD7YAaAD1NQjpVnUqEFtbC5bRnRXuG00Ef6M60az77DldZLemql7D9qG"
    "mw9GSA8V7Hqkh2T73iD8kK07qxB/oTIEJm3TH325/+Dut+jCzMmAdfa+is4F5FLBzwmWRL"
    "2UXwGwmcBmvoRwDbYtTaJh+foQCBQ79JDGGyju2gtVkqP++f9kKOgm"
)
