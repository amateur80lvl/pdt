#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

std::string hash_to_string(unsigned char* hash_ptr, unsigned int hash_size)
{
    static char hexdigits[] = "0123456789ABCDEF";
    std::string s;

    for(unsigned int i = 0; i < hash_size; i++) {
        unsigned char v = *hash_ptr++;
        s += hexdigits[v >> 4];
        s += hexdigits[v & 15];
    }
    return s;
}

class HashArray {
public:

    unsigned char *buffer;
    size_t num_elements;
    unsigned int hash_size;
    unsigned char *temp;

    inline unsigned char* hash_ptr(size_t i)
    {
        return &this->buffer[i * this->hash_size];
    }

    void swap(size_t i, size_t j)
    {
        memcpy(this->temp, this->hash_ptr(i), this->hash_size);
        memcpy(this->hash_ptr(i), this->hash_ptr(j), this->hash_size);
        memcpy(this->hash_ptr(j), this->temp, this->hash_size);
    }

    bool is_below(size_t i, size_t j)
    {
        return memcmp(this->hash_ptr(i), this->hash_ptr(j), this->hash_size) < 0;
    }

    size_t partition(size_t first, size_t last)
    {
        size_t i, j, pivot;

        pivot = last;
        i = first;
        for(j = first; j <= last; j++) {
            if(this->is_below(j, pivot)) {
                this->swap(i, j);
                i++;
            }
        }
        this->swap(i, last);
        return i;
    }

    void quicksort(size_t first, size_t last)
    {
        if(first < last) {
            size_t p = this->partition(first, last);
            if(p != 0) {
                this->quicksort(first, p - 1);
            }
            this->quicksort(p + 1, last);
        }
    }

    HashArray(unsigned char* buffer, size_t num_elements, unsigned int hash_size)
    {
        this->temp = new unsigned char(hash_size);
        this->buffer = buffer;
        this->num_elements = num_elements;
        this->hash_size = hash_size;
    }

    ~HashArray()
    {
        delete this->temp;
    }

    size_t get_num_elements()
    {
        return this->num_elements;
    }

    void sort()
    {
        this->quicksort(0, this->num_elements - 1);
    }

    std::string to_string(size_t i)
    {
        unsigned char *hash_ptr = this->hash_ptr(i);
        return hash_to_string(hash_ptr, this->hash_size);
    }
};

class HashCount {
private:
    unsigned int hash_size;
    unsigned char *hashes;
    size_t *counts;
    unsigned int num_items;
    unsigned int capacity;

public:

    HashCount(unsigned int hash_size)
    {
        this->hash_size = hash_size;
        this->hashes = NULL;
        this->counts = NULL;
        this->num_items = 0;
        this->capacity = 0;
    }

    ~HashCount()
    {
        if(this->hashes != NULL) {
            free(this->hashes);
        }
        if(this->counts != NULL) {
            free(this->counts);
        }
    }

    inline void increase(unsigned char* hash_ptr)
    {
        // find existing hash
        unsigned char *duplicate_hash = NULL;
        unsigned int duplicate_index;
        if(this->hashes != NULL) {
            unsigned char *other_hash_ptr = this->hashes;
            for(unsigned int i = 0; i < this->num_items; i++) {
                if(memcmp(other_hash_ptr, hash_ptr, this->hash_size) == 0) {
                    duplicate_hash = other_hash_ptr;
                    duplicate_index = i;
                    break;
                }
                other_hash_ptr += this->hash_size;
            }
        }

        if(duplicate_hash != NULL) {
            this->counts[duplicate_index]++;
            return;
        }

        // add new hash with count = 1
        if(this->num_items == this->capacity) {
            this->capacity += 8192;
            this->hashes = (unsigned char*) realloc(this->hashes, this->hash_size * this->capacity);
            this->counts = (size_t*) realloc(this->counts, sizeof(size_t) * this->capacity);
            if(this->hashes == NULL || this->counts == NULL) {
                fprintf(stderr, "Memory error\n");
                exit(1);
            }
        }
        memcpy(this->hashes + this->num_items * this->hash_size, hash_ptr, this->hash_size);
        this->counts[this->num_items] = 1;
        this->num_items++;
    }

    unsigned int get_num_items()
    {
        return this->num_items;
    }


    std::string to_string(unsigned int i)
    {
        std::string s;
        unsigned char *hash_ptr = this->hashes + this->hash_size * i;
        s = hash_to_string(hash_ptr, this->hash_size);
        s += ' ';
        s += std::to_string(this->counts[i]);
        return s;
    }
};

int main(int argc, char* argv[])
{
    char* filename;
    unsigned int hash_size;

    if(argc != 3) {
        fprintf(stderr, "Arguments required: <file name> <hash size>\n");
        return 1;
    }

    filename = argv[1];
    sscanf(argv[2], "%u", &hash_size);

    fprintf(stderr, "Opening file...\n");
    FILE *fp;
    size_t file_size;

    fp = fopen(filename, "rb");
    if(fp == NULL) {
        fprintf(stderr, "Cannot open %s\n", filename);
        return 1;
    }

    fseek(fp, 0, SEEK_END);
    file_size = ftell(fp);
    rewind(fp);

    if(file_size % hash_size != 0) {
        fprintf(stderr, "File size is not multiple of hash size\n");
        return 1;
    }

    unsigned char *buffer = (unsigned char*) malloc(file_size);  // new unsigned char(file_size) DOES NOT fail in case of OOM!!!
    if(buffer == NULL) {
        fprintf(stderr, "Memory error\n");
        return 1;
    }
    fprintf(stderr, "Reading %zu bytes\n", file_size);
    size_t size_read = 0;
    while(size_read != file_size) {
        size_t remain = file_size - size_read;
        size_t n = fread(buffer + size_read, 1, remain, fp);
        fprintf(stderr, "read %zu out of %zu\n", n, remain);
        if(n == 0) {
            fprintf(stderr, "Reading error\n");
            return 1;
        }
        size_read += n;
    }
    fclose(fp);
    fprintf(stderr, "Read %zu elements %u bytes each\n", file_size / hash_size, hash_size);

    fprintf(stderr, "Sorting hashes...\n");
    HashArray hash_array = HashArray(buffer, file_size / hash_size, hash_size);
    hash_array.sort();
    /*
    for(size_t i = 0; i < hash_array.get_num_elements(); i++) {
        std::string s = hash_array.to_string(i);
        puts(s.c_str());
    }
    */

    fprintf(stderr, "Finding collisions...\n");
    HashCount duplicate_hashes = HashCount(hash_size);
    unsigned char *prev_hash_ptr = hash_array.hash_ptr(0);
    for(size_t i = 1, j = hash_array.get_num_elements(); i < j; i++) {
        unsigned char *hash_ptr = hash_array.hash_ptr(i);
        if(memcmp(hash_ptr, prev_hash_ptr, hash_size) == 0) {
            duplicate_hashes.increase(hash_ptr);
            fprintf(stderr, ".");
        } else {
            prev_hash_ptr = hash_ptr;
        }
    }

    for(unsigned int i = 0, j = duplicate_hashes.get_num_items(); i < j; i++) {
        std::string s = duplicate_hashes.to_string(i);
        puts(s.c_str());
    }

    free(buffer);

    return 0;
}
