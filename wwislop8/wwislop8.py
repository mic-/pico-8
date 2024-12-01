#!/usr/bin/python

# What Would It Sound Like On PICO-8?
#
# Converts various music formats into PICO-8 __sfx__
# and __music__ data.
#
# Mic, 2024

import argparse
import re
import struct
import sys
from functools import reduce

class PICO8Pattern:
    class Row:
        def __init__(self, note, instrument, volume, effect):
            self.note = note
            self.instrument = instrument
            self.volume = volume
            self.effect = effect
        
        def format(self):
            if self.note is not None:
                return "%02x%d%d%d" % (self.note, self.instrument, self.volume, self.effect)
            else:
                return "00000"

    def __init__(self, speed):
        self.rows = [None] * 32
        self.speed = speed

    def set(self, row, note, instrument, volume, effect):
        self.rows[row] = PICO8Pattern.Row(note, instrument, volume, effect)

    def format(self):
        return reduce(lambda acc,row:
            acc + (row.format() if row is not None else "00000"),
            self.rows, "01%02x0000" % self.speed)


class PICO8Sequence:  
    def __init__(self):
        self.channels = [None] * 4

    def set(self, channel, pattern_to_play):
        self.channels[channel] = pattern_to_play

    def format(self):
        result = "00 "
        for i in range(0, 4):
            if self.channels[i] is not None:
                result += "%02x" % self.channels[i]
            else:
                result += "%02x" % (0x40 + i + 1)
        return result


class PICO8Song:
    def __init__(self, sequences, patterns):
        self.sequences = sequences
        self.patterns = patterns

    def output(self):
        print("__sfx__")
        for p in self.patterns:
            print(p.format())
        print("__music__")
        for s in self.sequences:
            print(s.format())


class FutureComposerModule:
    class Sample:
        def __init__(self, data):
            self.length = int.from_bytes(data[0:2], byteorder='big')
            self.loop_start = int.from_bytes(data[2:4], byteorder='big')
            self.loop_length = int.from_bytes(data[4:6], byteorder='big')
    
    class Voice:
        def __init__(self, num, data):
            self.num = num
            self.pattern = data[0]
            self.transpose = data[1]
            self.sound_transpose = data[2]

        def hash(self):
            return self.pattern + self.transpose*0x100 + self.sound_transpose*0x10000

    class Sequence:
        def __init__(self, data):
            self.voices = []
            self.voices.append(FutureComposerModule.Voice(0, data))
            self.voices.append(FutureComposerModule.Voice(1, data[3:]))
            self.voices.append(FutureComposerModule.Voice(2, data[6:]))
            self.voices.append(FutureComposerModule.Voice(3, data[9:]))
            self.speed = data[12]

    def __init__(self, args):
        self.args = args
        with open(args.input, mode='rb') as file:
            self.contents = file.read()
        self.magic = struct.unpack('4s', self.contents[:4])[0]
        if self.magic != b'SMOD' and self.magic != b'FC14':
            sys.exit("Unknown format: %s" % magic)

        self.sequence_data_size = int.from_bytes(self.contents[4:8], byteorder='big')
        self.pattern_offset = int.from_bytes(self.contents[8:12], byteorder='big')
        self.pattern_data_size = int.from_bytes(self.contents[12:16], byteorder='big')
        self.freqmod_offset = int.from_bytes(self.contents[16:20], byteorder='big')
        self.freqmod_data_size = int.from_bytes(self.contents[20:24], byteorder='big')
        self.volume_offset = int.from_bytes(self.contents[24:28], byteorder='big')
        self.volume_data_size = int.from_bytes(self.contents[28:32], byteorder='big')
        self.sample_offset = int.from_bytes(self.contents[32:36], byteorder='big')
        if self.magic == b'FC14':
            self.wavetable_offset = int.from_bytes(self.contents[36:40], byteorder='big')
            self.sequence_offset = 180
        elif self.magic == b'SMOD':
            self.sample_data_size = int.from_bytes(self.contents[36:40], byteorder='big')
            self.sequence_offset = 100

        self.samples = []
        for i in range(0,10):
            self.samples.append(self.Sample(self.contents[40+i*6:]))

        num_sequences = self.sequence_data_size // 13
        self.sequences = []
        for i in range(0, num_sequences):
            if i >= args.start and (i <= args.end or args.end == -1):
                self.sequences.append(self.Sequence(self.contents[self.sequence_offset+i*13:]))

        self.used_patterns = []
        for sequence in self.sequences:
            for voice in sequence.voices:
                hash = voice.hash()
                if hash not in self.used_patterns:
                    self.used_patterns.append(hash)
        if len(self.used_patterns) > 64:
            print("Warning: the number of unique patterns exceeds 64")

    def convert_patterns(self):
        pico8_patterns = []
        for used_pattern in self.used_patterns:
            pico8_pattern = PICO8Pattern(self.args.speed)
            pat_num = used_pattern & 0xFF
            pat_transpose = (used_pattern >> 8) & 0xFF
            offset = self.pattern_offset + pat_num*64
            pattern = self.contents[offset:offset+64]
            if pat_transpose >= 0x80:
                pat_transpose -= 256
            for row in range(0,32):
                note = pattern[row*2]
                if note > 0:
                    info = pattern[row*2 + 1]
                    note += 24  # FC notes start at C2, PICO-8 notes start at C0
                    note += pat_transpose + self.args.transpose
                    if note > 63:
                        print("Warning: found note above D#5 in pattern %d; clamping" % pat_num)
                        note = 63
                    if note < 0:
                        print("Warning: found note below C0 in pattern %d; clamping" % pat_num)
                        note = 0
                    instrument = info & 7
                    pico8_pattern.set(row, note, instrument, 4, 0)
            pico8_patterns.append(pico8_pattern)
        return pico8_patterns

    def convert_sequences(self):
        pico8_sequences = []
        for sequence in self.sequences:
            pico8_sequence = PICO8Sequence()
            for voice in sequence.voices:
                hash = voice.hash()
                pat_num = hash & 0xFF
                if pat_num > 0:
                    pico8_sequence.set(voice.num, self.used_patterns.index(hash))
            pico8_sequences.append(pico8_sequence)
        return pico8_sequences


parser = argparse.ArgumentParser(prog='wwislop8')
parser.add_argument('--start', help='The position in the input file to start transcribing from', default=0, type=int)
parser.add_argument('--end', help='The position in the input file to end transcribing at', default=-1, type=int)
parser.add_argument('--speed', help='The playback speed to assign to the PICO-8 patterns', default=10, type=int)
parser.add_argument('--transpose', help='The number of semitones to transpose all notes by', default=0, type=int)
parser.add_argument('input')
args = parser.parse_args()

module = FutureComposerModule(args)
pico8_song = PICO8Song(module.convert_sequences(), module.convert_patterns())

print("pico-8 cartridge // http://www.pico-8.com")
print("version 42")
print("__gfx__")
for i in range(0,6):
    print("00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000")

pico8_song.output()
