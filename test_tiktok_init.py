import json
import os
import sqlite3
import requests

def test():
    db_path = "/home/ubuntu/apps/database/users.db"
    access_token = None
    
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT access_token FROM tiktok_connections ORDER BY connected_at DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            access_token = row[0]
            print("Loaded access_token from users.db")
        conn.close()
        
    if not access_token:
        print("No access token found!")
        return
        
    init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    
    video_size = 171302532
    real_failed_title = "Você aceitaria esse pacto? 😳\n\nTitulo: Desconhecido\n\nSinopse: Quem diria que a linda assistente contratada por um bom dinheiro ganharia um ferrão misterioso logo após fazer hora extra com o rapaz. Pensando que ela tinha se machucado, o jovem tentou ajudar a tirar o espinho, mas acabou sendo transportado para outra dimensão assim que a tocou. Quando o rapaz estava quase caindo no abismo, a moça o puxou de volta bem a tempo, embora estivesse com uma cara nada amigável. Ela perguntou irritada por que ele tocou nela sem permissão, mas se acalmou ao ouvir que ele só queria ajudar após ficar tonto e ver coisas. Diante disso, a jovem finalmente relaxou, mas revelou que quem tocasse naquele ferrão seria obrigado a se casar com ela. Desde a morte do pai, o estudante precisou trabalhar como desenhista para cuidar dos irmãos mais novos, mas dar conta de tudo sozinho era difícil demais. Por causa da correria, ele mal conseguia se alimentar, até que um amigo ligou avisando que tinha achado uma ajudante, fazendo o rapaz sair correndo de casa. Ao chegar ao local combinado, ele ficou totalmente encantado com a beleza da moça, ficando sem reação por alguns segundos. Só quando ela se apresentou é que o jovem voltou a si e, sem perder tempo, entregou os materiais para começarem o trabalho logo. Apesar de parecer apenas um rostinho bonito, a nova funcionária se mostrou extremamente rápida e competente em todas as tarefas. Impressionado com tanta habilidade, o desenhista descobriu que ela aprendeu tudo sozinha lendo revistas, e resolveu testá-la em outras funções. Para sua surpresa, ela fez um trabalho impecável, deixando o rapaz tão aliviado e feliz que ele comemorou bastante antes dos irmãos voltarem da escola. Assim que as crianças chegaram e viram a bela visitante, decidiram mostrar a casa para ela, aproveitando a chance para elogiar o irmão mais velho. Com a intenção de ajudar no romance e facilitar o serviço, a moça acabou trazendo suas malas para passar uns dias morando ali. Em pouco tempo, ela conquistou o carinho dos pequenos, enquanto o jovem descobriu que sua nova parceira era, na verdade, uma grande fã de suas obras. No entanto, na véspera da entrega, o desenhista percebeu que faltava uma página importante, que acabou achando jogada em um canto escuro. Como a folha tinha apenas um rascunho e exigiria horas de dedicação, a assistente se ofereceu imediatamente para ajudar a terminar o desenho. A atitude generosa mexeu muito com ele, que sempre se sentiu sozinho por não poder contar com o apoio de outros parentes. Pensando no bem-estar de sua família, o rapaz finalmente deixou o orgulho de lado e aceitou a ajuda dela. Unindo forças, os dois trabalharam a noite toda e terminaram tudo bem no amanhecer, deixando o trabalho pronto para o envio. Exausto, o jovem acabou desmaiando de sono no chão, e ao acordar, acabou tocando sem querer no espinho misterioso da assistente. Quando ela insistiu que agora eles deviam se casar, ele pediu para parar com a brincadeira, mas a garota garantiu que falava sério. A moça explicou que conhecia a alma dele através de suas artes, mas o desenhista achou aquela conversa romântica um tanto absurda. Para resolver a situação, a jovem fez uma proposta irrecusável: que os dois começassem sendo apenas bons amigos.\n\n#anime #animerecap #resumodeanime #animeresumo #otaku #manhwa #webtoon #romanceanime"
    
    # Limpa a título para testar o texto base sem quebras de linha e com números diferentes de hashtags
    hook_only = "Você aceitaria esse pacto? 😳\n\n#anime #animerecap #resumodeanime #animeresumo #otaku #manhwa #webtoon #romanceanime"
    
    tests_trunc = [
        ("1. hook (113 chars)", hook_only),
        ("2. 500 chars", real_failed_title[:500]),
        ("3. 1000 chars", real_failed_title[:1000]),
        ("4. 1500 chars", real_failed_title[:1500]),
        ("5. 2000 chars", real_failed_title[:2000]),
        ("6. 2200 chars", real_failed_title[:2200]),
        ("7. texto original completo (2878 chars)", real_failed_title),
    ]
    
    for name, title_val in tests_trunc:
        payload = {
            "post_info": {
                "title": title_val,
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "disable_duet": True,
                "disable_stitch": True,
                "disable_comment": False
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": 60 * 1024 * 1024,
                "total_chunk_count": 2
            }
        }
        print(f"Testando {name} ({len(title_val)} chars)...")
        import time; time.sleep(2)  # evitar rate limit
        res = requests.post(init_url, headers=headers, json=payload)
        print(f"Status: {res.status_code}")
        print(f"Body: {res.text}\n")

if __name__ == "__main__":
    test()
