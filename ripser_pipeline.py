import numpy as np
import string
import re
from os import path

import gensim
from gensim.scripts.glove2word2vec import glove2word2vec

from allennlp.commands.elmo import ElmoEmbedder

import torch
from transformers import BertTokenizer, BertModel

import multiprocessing

import persim
from ripser import ripser
import matplotlib
from matplotlib import pyplot as plt

import argparse


parser = argparse.ArgumentParser(description="embed the text as a point cloud in the embedding space")
parser.add_argument('text', help='input text file')
parser.add_argument('-e', '--embed', action="store_true", help="save embedding vectors in numpy format")
parser.add_argument('-r', '--run', action="store_true", help="run ripser computation")
parser.add_argument('-d', '--dim', type=int, default=2, help="max dimension to run")
parser.add_argument('-n', '--sample', type=int, default=100, help="points to subsample")
args = parser.parse_args()


def tokenize_from_file(filename, keep_punct = False):
    with open(filename,"r") as file:
        text = file.read()
    if keep_punct is True:
        for punct in string.punctuation:
            text = text.replace(punct, ' ' + punct + ' ')
    else:
        for punct in string.punctuation:
            text = text.replace(punct, ' ')
    
    text = re.sub('\s+', ' ', text)
    
    result = []
    
    for x in text.lower().split(' '):
        if x.isalpha():
            result.append(x)
        else:
            word = []
            for y in x: # for every character
                if y.isalpha(): word.append(y)
            if len(word) > 0:
                result.append(''.join(word))
                
    return result

def get_vectors(wv, words):
    M = []
    for w in words:
        try:
            M.append(wv[w])
        except KeyError:
            continue
    M = np.stack(M)
    return M

def vectors_to_plex(vectors, filename):
    #dist_matrix = euclidean_distances(vectors)
    #vectors = vectors / np.mean(dist_matrix)
    with open(filename, "w") as out:
        #out.write(" ".join([str(i) for i in range(vectors.shape[1])]))
        #out.write("\n")
        for i, vector in enumerate(vectors):
            out.write(" ".join(map(str,vector)))
            out.write("\n")

def ripser_compute(points):
    return ripser(points, maxdim=args.dim, n_perm=args.sample)['dgms']

if __name__ == "__main__":
    text_name = args.text
    text_em = "embeddings/" + args.text
    text_results = "ripser_output/" + args.text
    text_filename = "texts/" + args.text
    text_words = tokenize_from_file(text_filename)

    print("read text of length " + str(len(text_words)) + " words...")

    if args.embed:

        #BERT
        print("embedding with BERT...")
        tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
        with open(text_filename, "r") as f:
            text = f.read()
        tokenized_text = [tokenizer.tokenize('[CLS] ' + x + ' [SEP]') for x in text.split('.')]
        indexed_tokens = [tokenizer.convert_tokens_to_ids(x) for x in tokenized_text]
        tokens_tensors = [torch.tensor([x]) for x in indexed_tokens]
        model = BertModel.from_pretrained('bert-base-uncased')
        model.eval()

        with torch.no_grad():
            outputs = [model(x) for x in tokens_tensors]
            bert_embeddings = torch.stack([x for output in outputs for x in output[0][0][1:-1]])
        
        np.save(text_em + ".bert", bert_embeddings.numpy())   

        #word2vec
        print("embedding with word2vec...")
        word2vec_model = gensim.models.KeyedVectors.load_word2vec_format('./data/GoogleNews-vectors-negative300.bin', \
                                                                         binary=True)  
        word2vec_embeddings = get_vectors(word2vec_model, text_words)
        np.save(text_em + ".word2vec", word2vec_embeddings)                                                           

        #GLoVe
        print("embedding with GloVe...")
        glove6 = "data/glove.6B.300d.gensim.txt"
        glove840 = "data/glove.840B.300d.gensim.txt"
        if not (path.exists(glove6) and path.exists(glove840)):
            glove2word2vec(glove_input_file="data/glove.6B.300d.txt", word2vec_output_file=glove6)
            glove2word2vec(glove_input_file="data/glove.840B.300d.txt", word2vec_output_file=glove840)
        glove_cc_model = gensim.models.KeyedVectors.load_word2vec_format(glove6, binary=False)
        glove_wiki_model = gensim.models.KeyedVectors.load_word2vec_format(glove840, binary=False)

        glove_cc_embeddings = get_vectors(glove_cc_model, text_words)
        glove_wiki_embeddings = get_vectors(glove_wiki_model, text_words)
        
        np.save(text_em + ".glove_cc", glove_cc_embeddings)
        np.save(text_em + ".glove_wiki", glove_wiki_embeddings)

        #ELMo
        print("embedding with ELMo")
        elmo_embedder = ElmoEmbedder(options_file="data/elmo_2x2048_256_2048cnn_1xhighway_options.json", \
                                weight_file="data/elmo_2x2048_256_2048cnn_1xhighway_weights.hdf5")

        elmo_embeddings_raw = elmo_embedder.embed_sentence(text_words)

        elmo_embeddings = elmo_embeddings_raw[2]

        np.save(text_em + ".elmo", elmo_embeddings)

        # prepare for Plex
        vectors_to_plex(word2vec_embeddings, filename="plex_input/" + text_name + ".word2vec_plex")
        vectors_to_plex(glove_cc_embeddings, filename="plex_input/" + text_name + ".glove_cc_plex")
        vectors_to_plex(glove_wiki_embeddings, filename="plex_input/" + text_name + ".glove_wiki_plex")
        vectors_to_plex(elmo_embeddings, filename="plex_input/" + text_name + ".elmo_plex")
        vectors_to_plex(bert_embeddings, filename="plex_input/" + text_name + ".bert_plex")

    # load embeddings
    word2vec_embeddings = np.load(text_em + ".word2vec.npy")
    glove_wiki_embeddings = np.load(text_em + ".glove_wiki.npy")
    glove_cc_embeddings = np.load(text_em + ".glove_cc.npy")
    elmo_embeddings = np.load(text_em + ".elmo.npy")
    bert_embeddings = np.load(text_em + ".bert.npy")

    if args.run:

        print("launching ripser in parallel")
        pool = multiprocessing.Pool()
        diagrams = pool.map(ripser_compute, [word2vec_embeddings, glove_wiki_embeddings, 
                     glove_cc_embeddings, elmo_embeddings, bert_embeddings])
        pool.close()

        print("making plots")
        plt.figure(figsize=(25,8))
        plt.subplot(151)
        persim.plot_diagrams(diagrams[0])
        plt.title("word2vec")

        plt.subplot(152)
        persim.plot_diagrams(diagrams[1])
        plt.title("GLoVe Wiki")

        plt.subplot(153)
        persim.plot_diagrams(diagrams[2])
        plt.title("GloVe CC")

        plt.subplot(154)
        persim.plot_diagrams(diagrams[3])
        plt.title("ELMo")

        plt.subplot(155)
        persim.plot_diagrams(diagrams[4])
        plt.title("BERT")

        plt.savefig(text_results + "-plots.pdf", dpi=500)

        print("writing output")
        for i, emb in enumerate(["word2vec", "glove_wiki", "glove_cc", "elmo", "bert"]):
            with open(text_results + "." + emb,"w") as f:
                for dim in diagrams[i]:
                    for interval in dim:
                        f.write(str(interval[0])+" "+str(interval[1])+"\n")
                    f.write("\n")

