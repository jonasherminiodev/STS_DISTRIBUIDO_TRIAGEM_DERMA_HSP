# Sistema Distribuído para Triagem Dermatológica e Fototerapia Hospitalar

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![gRPC](https://img.shields.io/badge/gRPC-HTTP%2F2-green.svg)](https://grpc.io/)
[![Protocol Buffers](https://img.shields.io/badge/Protobuf-v4.25-orange.svg)](https://protobuf.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Projeto prático desenvolvido para a disciplina de **Distribuição de Processos e Dados (Sistemas Distribuídos)** do Departamento de Computação da **Universidade Federal do Ceará (UFC)**, ministrada pelo **Prof. Dr. Paulo A. L. Rego**.

---

## 📌 Sobre o Projeto

Este sistema implementa uma solução distribuída para **monitoramento hospitalar, controle operacional e triagem clínica com Inteligência Artificial na borda (*Edge AI*)**.

O projeto reaproveita e expande um projeto prévio autoral de classificação de lesões de pele com Deep Learning, desacoplando o modelo convolucional Keras de sua antiga estrutura monolítica para atuar como um dispositivo inteligente de borda dentro de uma rede heterogênea de nós autônomos.

### Principais Características da Arquitetura:
* **Processos Independentes:** Todos os componentes rodam como processos separados do Sistema Operacional (PIDs isolados), comunicando-se exclusivamente via rede.
* **Comunicação Cliente–Gateway (TCP puro):** Conexão confiável na porta `8000/TCP` com enquadramento de mensagens (*Length-Prefixed Framing* de 4 bytes Big-Endian).
* **Telemetria Contínua (UDP Unicast):** Fluxos contínuos e de baixa sobrecarga na porta `9000/UDP`.
* **Descoberta Dinâmica (UDP Multicast):** Reconhecimento *plug-and-play* de novos nós via grupo multicast `224.1.1.1:10000`.
* **Controle Remoto (gRPC sobre HTTP/2):** Chamadas remotas tipadas na porta `50051` para reconfigurar parâmetros operacionais das fontes.
* **Serialização Padronizada:** 100% das mensagens utilizam contratos **Protocol Buffers (`.proto`)**.
* **Tolerância a Falhas:** Monitoramento assíncrono de inatividade (*heartbeat*) no Gateway com timeout de 20s para detecção automática de nós offline.

---

## 🏥 Os Componentes do Sistema (As Três Partes)

```
                 +-------------------------------------------------------+
                 |                       CLIENTES                        |
                 |  - Interface em Linha de Comando (CLI Interativa)     |
                 |  - Dashboard Web com Séries Temporais (:5050 Chart.js)|
                 +---------------------------+---------------------------+
                                             |
                                             | TCP Socket (:8000)
                                             | [Length-Prefixed Framing + Protobuf]
                                             v
                 +-------------------------------------------------------+
                 |                    GATEWAY CENTRAL                    |
                 |  - Orquestrador e Servidor TCP Multithread (:8000)    |
                 |  - Receptor de Telemetria UDP (:9000)                 |
                 |  - Descoberta UDP Multicast (224.1.1.1:10000)         |
                 |  - Motor de 3 Consultas Analíticas Agregadas          |
                 |  - Persistência em SQLite (telemetry_history.db)      |
                 +-----------+-------------------------------+-----------+
                             |                               |
      gRPC Control (:50051)  |       UDP Telemetry           | UDP Multicast Discovery
      [Configure / State]    |       Unicast (:9000)         | (Solicitação / Resposta)
                             |                               |
                             v                               v
 +---------------------------------------------------------------------------------------+
 |                            FONTES DE DADOS DISTRIBUÍDAS                               |
 |                                                                                       |
 |  [FONTE 1: Controlável]        [FONTE 2: Contínua]         [FONTE 3: Alerta Imediato] |
 |  Estação Dermatoscopia IA      Sensor Cabine UV / Clima    Patch Dérmico Pós-Biópsia  |
 |  - Servidor gRPC (:50051)      - Envio contínuo UDP (5s)   - Envio periódico UDP      |
 |  - Modelo Keras tcc.h5 (Edge)  - Radiação UVA/UVB, Temp.   - Disparo IMEDIATO em caso |
 |  - Classifica 7 patologias       e Umidade da sala           de febre (> 38.5 °C)     |
 +---------------------------------------------------------------------------------------+
```

### 1. Gateway Central
Atua como ponto central de orquestração clínica. Agrega telemetrias, monitora a saúde das fontes via heartbeat, armazena o histórico em SQLite e responde às consultas do cliente.

### 2. Três Fontes de Dados Distribuídas
1. **Fonte 1 (Controlável via gRPC `:50051`) — Estação de Dermatoscopia Digital com IA:**  
   Executa a rede neural Keras localmente na borda e classifica lesões de pele em **7 categorias diagnósticas**:
   * *Queratoses actínicas (`akiec`), Carcinoma basocelular (`bcc`), Dermatofibroma (`df`), Queratose benigna (`bkl`), Melanoma (`mel`), Nevos melanocíticos (`nv`) e Lesões vasculares (`vasc`)*.  
   Recebe comandos gRPC para mudar frequência de envio, limiar de malignidade ou pausar.
2. **Fonte 2 (Não Controlável) — Sensor de Cabine UV / Fototerapia:**  
   Envia periodicamente a cada 5 segundos leituras de dosimetria de radiação UVA/UVB, temperatura e umidade da sala via UDP.
3. **Fonte 3 (Evento Crítico Imediato) — Patch Dérmico Pós-Biópsia:**  
   Monitora a temperatura tecidual pós-operatória. Caso detecte febre aguda ($T > 38.5^\circ\text{C}$), quebra o ciclo de espera e **transmite na mesma fração de segundo um pacote UDP de emergência**.

### 3. Clientes
* **Cliente CLI (`cli_client.py`):** Menu interativo no terminal conectado ao Gateway via TCP para listar nós, enviar comandos gRPC e executar as 3 consultas analíticas.
* **Cliente Web Dashboard (`web_app.py` - Bônus):** Interface moderna em Flask (`:5050`) conectada ao Gateway via TCP, com gráficos interativos de séries temporais gerados por Chart.js.

---

## 🚀 Como Executar o Projeto

### Pré-requisitos
* Python 3.9 ou superior
* Sistema Operacional: macOS ou Linux (ou Windows com WSL)

### 1. Clonar o Repositório e Instalar Dependências

Clone o repositório e acesse a pasta do projeto:
```bash
git clone <https://github.com/jonasherminiodev/STS_DISTRIBUIDO_TRIAGEM_DERMA_HSP>
cd STS_DISTRIBUIDO_CANCER_PELE
```

O sistema pode ser executado em dois modos:

#### A) Modo Simulado (Recomendado — Leve e Rápido)
Não exige instalação do TensorFlow nem GPU. As predições da Fonte 1 usam amostragem probabilística sintética idêntica ao comportamento real do modelo:
```bash
pip install grpcio protobuf flask pillow numpy
```

#### B) Modo Real (Inferência com Deep Learning e `tcc.h5`)
Caso deseje que a Fonte 1 carregue a rede neural convolucional ResNet-152v2 real:
1. **Instale as dependências de Machine Learning:**
   ```bash
   pip install grpcio protobuf flask pillow numpy
   pip install -r "ANALISE_IMG_CANCER_DE_PELE /requirements.txt"
   # Ou alternativamente: pip install tensorflow keras
   ```

2. **Download dos pesos do modelo (`tcc.h5`):**
   Como o arquivo de modelo (`tcc.h5`, ~220 MB) é ignorado pelo Git via `.gitignore`, faça o download diretamente no Hugging Face:
   * 🔗 **Link no Hugging Face:** [https://huggingface.co/jonasherminio/resnet152v2-skin-cancer-ham10000](https://huggingface.co/jonasherminio/resnet152v2-skin-cancer-ham10000)
   * Baixe o arquivo `tcc.h5` e cole dentro da pasta do modelo:
     `ANALISE_IMG_CANCER_DE_PELE /tcc.h5`

---

### 2. Execução Passo a Passo (Terminais Separados)

Abra terminais independentes na pasta raiz do projeto:

#### Terminal 1: Iniciar o Gateway Central
```bash
cd distributed
./run_gateway.sh
```
*O Gateway inicializa os sockets nas portas `8000/TCP`, `9000/UDP`, `224.1.1.1:10000/UDP` e o banco SQLite.*

---

#### Terminal 2: Fonte 1 — Estação de Dermatoscopia IA

* **Opção A — Modo Real (Carregando o modelo Keras `tcc.h5`):**  
  *(Requer o `tcc.h5` baixado do Hugging Face e dependências do `requirements.txt` instaladas)*
  ```bash
  cd distributed
  ./run_sources.sh --source 1 --grpc-port 50051
  ```

* **Opção B — Modo Simulado (Leve e rápido, sem necessidade do `.h5`):**  
  *(Ideal para avaliação rápida em qualquer máquina)*
  ```bash
  cd distributed
  ./run_sources.sh --source 1 --simulate-ai --grpc-port 50051
  ```

---

#### Terminal 3: Fonte 2 — Sensor de Cabine UV
```bash
cd distributed
./run_sources.sh --source 2
```

---

#### Terminal 4: Fonte 3 — Patch Dérmico Pós-Biópsia
```bash
cd distributed
./run_sources.sh --source 3
```

> **Dica:** Para iniciar todas as 3 fontes simultaneamente em um único terminal para testes rápidos, use `./run_sources.sh --source all` (ou `./run_sources.sh --source all --simulate-ai`).

---

#### Terminal 5: Iniciar o Cliente CLI
```bash
cd distributed
./run_client_cli.sh
```

No menu do terminal:
* Digite `1`: Listar todas as fontes conectadas e seus estados.
* Digite `2`: Despachar comandos remotos gRPC para a Fonte 1 (ajustar frequência de amostragem, limiar ou pausar).
* Digite `3`: Executar Consulta 1 (Resumo de Triagem de Malignidade da IA e as 7 classes).
* Digite `4`: Executar Consulta 2 (Médias e desvios padrão $\mu \pm \sigma$ de dosimetria UVA/UVB e clima).
* Digite `5`: Executar Consulta 3 (Ranking de incidentes e nó mais instável).

---

#### Terminal 6 (Opcional): Iniciar o Dashboard Web Interativo
```bash
cd distributed
./run_web_dashboard.sh
```
Abra no navegador: **`http://127.0.0.1:5050`**

---

## 🧪 Executando os Testes Automatizados

O sistema conta com uma suíte de testes de integração com sockets reais:

```bash
cd distributed
./run_all_tests.sh
```
